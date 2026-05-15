# compare_join_engines.py
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum, auto
import time
import threading


@dataclass
class Metrics:
    name: str
    rows_out: int = 0
    blocked_count: int = 0
    blocked_time: float = 0.0
    cpu_steps: int = 0
    wall_time: float = 0.0


# -----------------------------
# Volcano prototype
# -----------------------------
class VolcanoHashJoin:
    def __init__(self, left_rows, right_rows, key="k", wait_every=0, wait_s=0.002):
        self.left = left_rows
        self.right = right_rows
        self.key = key
        self.wait_every = wait_every
        self.wait_s = wait_s
        self.ht = defaultdict(list)
        self.i = 0
        self.pending = []

    def run(self, m: Metrics):
        t0 = time.perf_counter()

        # build barrier: 同步执行，卡在算子内部
        for idx, r in enumerate(self.right, start=1):
            m.cpu_steps += 1
            if self.wait_every and idx % self.wait_every == 0:
                m.blocked_count += 1
                b0 = time.perf_counter()
                time.sleep(self.wait_s)  # 模拟非IO等待（内存/锁/spill）
                m.blocked_time += time.perf_counter() - b0
            self.ht[r[self.key]].append(r)

        # probe
        for l in self.left:
            m.cpu_steps += 1
            matches = self.ht.get(l[self.key], [])
            m.rows_out += len(matches)

        m.wall_time = time.perf_counter() - t0


# -----------------------------
# Pipeline prototype
# -----------------------------
class State(Enum):
    READY = auto()
    RUNNING = auto()
    BLOCKED = auto()
    FINISHED = auto()


class Scheduler:
    def __init__(self):
        self.ready = deque()
        self.waiters = defaultdict(list)

    def submit(self, d):
        d.state = State.READY
        self.ready.append(d)

    def block_on(self, d, event):
        d.state = State.BLOCKED
        self.waiters[event].append(d)

    def fire(self, event):
        for d in self.waiters.pop(event, []):
            d.state = State.READY
            self.ready.append(d)

    def run(self):
        while self.ready or self.waiters:
            if self.ready:
                d = self.ready.popleft()
                d.state = State.RUNNING
                r = d.step(self)
                if r == "YIELD":
                    d.state = State.READY
                    self.ready.append(d)
                elif r == "FINISH":
                    d.state = State.FINISHED
            else:
                # 无 ready driver，等事件
                time.sleep(0.0005)


class BuildDriver:
    def __init__(self, right_rows, ht, m: Metrics, key="k", quantum=128, wait_every=0, wait_s=0.002):
        self.rows = right_rows
        self.ht = ht
        self.m = m
        self.key = key
        self.quantum = quantum
        self.wait_every = wait_every
        self.wait_s = wait_s
        self.i = 0
        self.state = State.READY

    def step(self, sch: Scheduler):
        budget = self.quantum
        while budget > 0 and self.i < len(self.rows):
            self.i += 1
            r = self.rows[self.i - 1]
            self.m.cpu_steps += 1
            self.ht[r[self.key]].append(r)
            budget -= 1

            if self.wait_every and self.i % self.wait_every == 0:
                self.m.blocked_count += 1
                b0 = time.perf_counter()
                sch.block_on(self, "mem_ready")
                # 让后台线程稍后唤醒（模拟异步事件）
                threading.Timer(self.wait_s, lambda: sch.fire("mem_ready")).start()
                self.m.blocked_time += time.perf_counter() - b0
                return "BLOCKED"

        if self.i >= len(self.rows):
            sch.fire("build_done")
            return "FINISH"
        return "YIELD"


class ProbeDriver:
    def __init__(self, left_rows, ht, m: Metrics, key="k", quantum=128):
        self.rows = left_rows
        self.ht = ht
        self.m = m
        self.key = key
        self.quantum = quantum
        self.i = 0
        self.started = False
        self.state = State.READY

    def step(self, sch: Scheduler):
        if not self.started:
            self.started = True
            sch.block_on(self, "build_done")
            return "BLOCKED"

        budget = self.quantum
        while budget > 0 and self.i < len(self.rows):
            l = self.rows[self.i]
            self.i += 1
            self.m.cpu_steps += 1
            self.m.rows_out += len(self.ht.get(l[self.key], []))
            budget -= 1

        if self.i >= len(self.rows):
            return "FINISH"
        return "YIELD"


def run_pipeline(left_rows, right_rows, key="k", wait_every=0, wait_s=0.002):
    m = Metrics(name="pipeline")
    t0 = time.perf_counter()

    ht = defaultdict(list)
    sch = Scheduler()
    sch.submit(BuildDriver(right_rows, ht, m, key=key, wait_every=wait_every, wait_s=wait_s))
    sch.submit(ProbeDriver(left_rows, ht, m, key=key))
    sch.run()

    m.wall_time = time.perf_counter() - t0
    return m


def run_volcano(left_rows, right_rows, key="k", wait_every=0, wait_s=0.002):
    m = Metrics(name="volcano")
    VolcanoHashJoin(left_rows, right_rows, key=key, wait_every=wait_every, wait_s=wait_s).run(m)
    return m


def main():
    # 同一份数据
    left = [{"k": i % 500} for i in range(80_000)]
    right = [{"k": i % 500} for i in range(80_000)]

    # 每 N 条触发一次“非IO等待”
    wait_every = 4000
    wait_s = 0.003

    mv = run_volcano(left, right, wait_every=wait_every, wait_s=wait_s)
    mp = run_pipeline(left, right, wait_every=wait_every, wait_s=wait_s)

    print("name      rows_out   cpu_steps   blocked_count   blocked_time(s)   wall_time(s)")
    for m in (mv, mp):
        print(f"{m.name:8} {m.rows_out:9d} {m.cpu_steps:10d} {m.blocked_count:14d} "
              f"{m.blocked_time:16.6f} {m.wall_time:12.6f}")


if __name__ == "__main__":
    main()
