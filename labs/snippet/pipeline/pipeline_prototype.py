# pipeline_prototype.py
from collections import deque, defaultdict
from enum import Enum, auto
import time


class State(Enum):
    READY = auto()
    RUNNING = auto()
    BLOCKED = auto()
    FINISHED = auto()


class Scheduler:
    def __init__(self):
        self.ready = deque()
        self.waiters = defaultdict(list)
        self.now = 0

    def submit(self, driver):
        driver.state = State.READY
        self.ready.append(driver)

    def block_on(self, driver, event):
        driver.state = State.BLOCKED
        self.waiters[event].append(driver)

    def fire(self, event):
        for d in self.waiters.pop(event, []):
            d.state = State.READY
            self.ready.append(d)

    def run(self):
        while self.ready or self.waiters:
            if self.ready:
                d = self.ready.popleft()
                d.state = State.RUNNING
                result = d.step(self)  # 一个时间片
                if result == "YIELD":
                    d.state = State.READY
                    self.ready.append(d)
                elif result == "FINISH":
                    d.state = State.FINISHED
            else:
                # 没有ready任务，事件循环推进
                time.sleep(0.005)
                self.now += 1


class BuildDriver:
    def __init__(self, right_rows, ht):
        self.rows = right_rows
        self.ht = ht
        self.i = 0

    def step(self, sch):
        # 每个时间片只处理一小批，避免独占
        budget = 2
        while budget > 0 and self.i < len(self.rows):
            r = self.rows[self.i]
            self.i += 1
            budget -= 1
            # 模拟非IO等待：比如内存仲裁未通过
            if r.get("need_wait"):
                sch.block_on(self, "mem_available")
                return "BLOCKED"
            self.ht[r["k"]].append(r)

        if self.i >= len(self.rows):
            sch.fire("join_build_done")  # barrier 变成显式事件
            return "FINISH"
        return "YIELD"


class ProbeDriver:
    def __init__(self, left_rows, ht):
        self.rows = left_rows
        self.ht = ht
        self.i = 0
        self.started = False

    def step(self, sch):
        if not self.started:
            # build没完成 -> 挂起，不占线程
            sch.block_on(self, "join_build_done")
            self.started = True
            return "BLOCKED"

        budget = 2
        while budget > 0 and self.i < len(self.rows):
            l = self.rows[self.i]
            self.i += 1
            budget -= 1
            for r in self.ht.get(l["k"], []):
                print("JOIN:", l, r)

        if self.i >= len(self.rows):
            return "FINISH"
        return "YIELD"


if __name__ == "__main__":
    ht = defaultdict(list)
    right = [{"k": 1, "rv": "x"}, {"k": 1, "rv": "y"}, {"k": 2, "rv": "z", "need_wait": True}]
    left = [{"k": 1, "lv": "a"}, {"k": 2, "lv": "b"}]

    sch = Scheduler()
    build = BuildDriver(right, ht)
    probe = ProbeDriver(left, ht)
    sch.submit(build)
    sch.submit(probe)

    # 模拟稍后内存可用
    def delayed_mem_release():
        time.sleep(0.03)
        sch.fire("mem_available")

    import threading
    threading.Thread(target=delayed_mem_release, daemon=True).start()

    sch.run()
