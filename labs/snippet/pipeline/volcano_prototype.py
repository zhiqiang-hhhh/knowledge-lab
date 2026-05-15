# volcano_prototype.py
from collections import defaultdict
import time


class Operator:
    def open(self): ...
    def next(self): ...
    def close(self): ...


class Scan(Operator):
    def __init__(self, rows):
        self.rows = rows
        self.i = 0

    def open(self):
        self.i = 0

    def next(self):
        if self.i >= len(self.rows):
            return None
        r = self.rows[self.i]
        self.i += 1
        return r

    def close(self):
        pass


class HashJoin(Operator):
    """R build, L probe。build barrier 被藏在 open() 里。"""
    def __init__(self, left, right, lk, rk):
        self.left = left
        self.right = right
        self.lk = lk
        self.rk = rk
        self.ht = defaultdict(list)
        self.pending = []

    def open(self):
        self.right.open()
        # barrier: build 全做完，probe 才能开始
        while True:
            r = self.right.next()
            if r is None:
                break
            # 模拟非IO长等待（比如内存紧张/spill/锁）
            time.sleep(0.01)
            self.ht[r[self.rk]].append(r)
        self.right.close()
        self.left.open()

    def next(self):
        if self.pending:
            return self.pending.pop()

        while True:
            l = self.left.next()
            if l is None:
                return None
            ms = self.ht.get(l[self.lk], [])
            if not ms:
                continue
            for r in ms[1:]:
                self.pending.append((l, r))
            return (l, ms[0])

    def close(self):
        self.left.close()


if __name__ == "__main__":
    L = Scan([{"k": 1, "lv": "a"}, {"k": 2, "lv": "b"}])
    R = Scan([{"k": 1, "rv": "x"}, {"k": 1, "rv": "y"}])
    j = HashJoin(L, R, "k", "k")
    j.open()
    while True:
        row = j.next()
        if row is None:
            break
        print(row)
    j.close()
