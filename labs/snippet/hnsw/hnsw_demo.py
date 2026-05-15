import numpy as np
import heapq
import random
import argparse
import time
import logging
from collections import Counter

def setup_logger(level=logging.INFO):
    logger = logging.getLogger("HNSW")
    if logger.handlers:
        logger.setLevel(level)
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler()
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger

class HNSW:
    def __init__(self, dim, M=4, ef=10, logger=None, verbose=False):
        self.dim = dim           # 向量维度
        self.M = M               # 每层最大连接数
        self.ef = ef             # 搜索候选大小
        self.levels = []         # 每个节点的最大层数
        self.graph = []          # graph[i][level] = 邻居列表
        self.vectors = []        # 数据存储
        self.enter_point = None  # 入口节点
        self.max_level = -1      # 当前最高层
        self.logger = logger or setup_logger(logging.INFO)
        self.verbose = verbose

    def _distance(self, a, b):
        return np.linalg.norm(a - b)

    def _random_level(self, prob=0.5):
        # 按几何分布随机生成节点层数
        level = 0
        while random.random() < prob:
            level += 1
        return level

    def add(self, vec):
        idx = len(self.vectors)
        self.vectors.append(vec)
        level = self._random_level()
        self.levels.append(level)
        self.graph.append([[] for _ in range(level + 1)])

        if self.enter_point is None:
            self.enter_point = idx
            self.max_level = level
            self.logger.info(f"add first node idx={idx}, level={level} -> set enter_point")
            return

        cur = self.enter_point
        # 1️⃣ 从最高层向下贪心找更近的入口
        for l in range(self.max_level, level - 1, -1):
            self.logger.debug(f"[add] idx={idx} greedy at level={l}, start cur={cur}")
            changed = True
            while changed:
                changed = False
                # 遍历当前入口的每一层的邻居节点
                for nb in self.graph[cur][l]:
                    # 如果入口的某个邻居距离 vec 更近，那么就把入口改成这个邻居
                    if self._distance(vec, self.vectors[nb]) < self._distance(vec, self.vectors[cur]):
                        self.logger.debug(f"[add] idx={idx} level={l} move {cur} -> {nb}")
                        cur = nb
                        changed = True

        # 2️⃣ 在每一层连接近邻
        # 思路（简化版 HNSW efConstruction）：
        #   - 从上一阶段贪心搜索得到的入口 cur 出发，在当前层 l 上做一个受 ef 限制的“局部扩展”。
        #   - 使用一个小根堆 candidates 按 (与新点 vec 的距离, 节点 id) 排序，反复弹出当前离 vec 最近的节点，
        #     将其邻居加入候选，这样 frontier 会在 vec 附近扩张。
        #   - visited 记录已访问节点，避免重复。
        #   - 当候选堆大小尚小于 ef 时，放宽拓展条件以扩大覆盖面；否则仅在发现更近的点时才继续扩展。
        #   - 最终从 visited 中选出与 vec 最近的 M 个点作为该层的连边（双向添加）。
        # 说明：这是教学用的直观版本，真实 HNSW 的邻居选择策略会更精细（例如有启发式裁剪等）。
        for l in range(min(level, self.max_level) + 1):
            # 初始化候选：从 cur 节点开始，其到新向量 vec 的距离作为堆键
            # candidates 是一个 list，存储 (distance, node_id) 元组，作为小根堆使用
            candidates = [(self._distance(vec, self.vectors[cur]), cur)]
            visited = {cur}
            # 受限扩展：围绕离 vec 最近的点向外“泛洪”到其邻居
            while candidates:
                d, node = heapq.heappop(candidates)  # 当前已发现的、距离 vec 最近的一个节点
                # 遍历该节点在当前层的所有邻居，尝试把更靠近 vec 的邻居推进候选堆
                for nb in self.graph[node][l]:
                    if nb not in visited:
                        visited.add(nb)
                        dist = self._distance(vec, self.vectors[nb])
                        # 拓展准则：
                        #   - 如果发现了更近的点 (dist < d)，一定推进，保持“向更近处扩张”的趋势；
                        #   - 或者候选堆尚未“填满” ef，则放宽准入以保证足够的覆盖/多样性。
                        if dist < d or len(candidates) < self.ef:
                            heapq.heappush(candidates, (dist, nb))
            # 根据已访问集合（候选扩展范围）选择 M 个最近邻作为连边目标
            # 注：真实实现通常会采用启发式选择以减少互相“过近”的冗余边，这里用简单的 Top-M 最近邻近似之。
            neighbors = sorted([(self._distance(vec, self.vectors[x]), x) for x in visited])[:self.M]
            # 新节点在该层的邻居列表（有向存储），与下行的反向添加共同形成“近似无向”的边
            self.graph[idx][l] = [x for _, x in neighbors]
            # 反向连边：将新节点 idx 追加到对端节点的邻居中
            # 注意：这里没有对旧节点的度做裁剪，故其度数可能临时超过 M（简化处理，用于演示）。
            for _, x in neighbors:
                self.graph[x][l].append(idx)
            self.logger.info(f"[add] idx={idx} level={l} connect {len(neighbors)} neighbors -> {self.graph[idx][l]}")

        if level > self.max_level:
            self.max_level = level
            self.enter_point = idx
            self.logger.info(f"[add] idx={idx} new max_level={self.max_level}, update enter_point={idx}")

    def search(self, query, k=1):
        cur = self.enter_point
        self.logger.info(f"[search] start from enter_point={cur}, max_level={self.max_level}, k={k}")
        # 1️⃣ 从最高层向下贪心搜索
        for l in range(self.max_level, 0, -1):
            changed = True
            while changed:
                changed = False
                for nb in self.graph[cur][l]:
                    if self._distance(query, self.vectors[nb]) < self._distance(query, self.vectors[cur]):
                        self.logger.debug(f"[search] level={l} move {cur} -> {nb}")
                        cur = nb
                        changed = True
        # 2️⃣ 在底层做 ef 扩展搜索
        candidates = [(self._distance(query, self.vectors[cur]), cur)]
        visited = {cur}
        results = []
        self.logger.debug(f"[search] base layer start from {cur}")
        while candidates:
            d, node = heapq.heappop(candidates)
            results.append((d, node))
            for nb in self.graph[node][0]:
                if nb not in visited:
                    visited.add(nb)
                    dist = self._distance(query, self.vectors[nb])
                    heapq.heappush(candidates, (dist, nb))
        topk = [node for _, node in sorted(results)[:k]]
        self.logger.info(f"[search] visited={len(visited)}, candidates_explored={len(results)}, topk={topk}")
        return topk


def compute_level_counts(levels):
    """统计每个节点的最大层（level）分布。
    返回 (xs, ys, counter)：
      - xs: 层编号 0..max_level
      - ys: 对应每层拥有该最大层的节点数量
      - counter: 原始 Counter(level -> count)
    """
    if not levels:
        return [], [], Counter()
    ctr = Counter(levels)
    max_lv = max(levels)
    xs = list(range(max_lv + 1))
    ys = [ctr.get(lv, 0) for lv in xs]
    return xs, ys, ctr


def plot_level_distribution(levels, out_file: str = None, show: bool = False, logger: logging.Logger = None):
    """绘制随机层分布柱状图。
    - levels: 每个节点的最大层数组（来自 hnsw.levels）
    - out_file: 保存图片路径（为 None 则不保存）
    - show: 是否弹窗显示（服务器/无显示环境下建议 False）
    - logger: 可选日志器
    """
    xs, ys, ctr = compute_level_counts(levels)
    total = len(levels)
    if logger:
        logger.info(f"level distribution: total_nodes={total}, max_level={max(xs) if xs else -1}, counts={dict(ctr)}")

    try:
        import matplotlib.pyplot as plt
    except Exception as e:
        if logger:
            logger.warning(f"matplotlib 不可用，跳过绘图: {e}")
        return

    plt.figure(figsize=(8, 5))
    plt.bar(xs, ys, color='tab:blue', alpha=0.8)
    plt.xlabel('Level (max level per node)')
    plt.ylabel('Count')
    plt.title('HNSW Random Level Distribution')
    plt.grid(True, axis='y', alpha=0.3)

    if out_file:
        try:
            plt.tight_layout()
            plt.savefig(out_file, dpi=200, bbox_inches='tight')
            if logger:
                logger.info(f"level distribution figure saved to: {out_file}")
        except Exception as e:
            if logger:
                logger.warning(f"保存图片失败: {e}")

    if show:
        try:
            plt.show()
        except Exception:
            # 在无显示环境可能失败，忽略
            pass

def main():
    parser = argparse.ArgumentParser(description="Minimal HNSW demo with logging")
    parser.add_argument("--dim", type=int, default=16, help="vector dimension")
    parser.add_argument("--N", type=int, default=500, help="number of database vectors")
    parser.add_argument("--queries", type=int, default=3, help="number of query vectors")
    parser.add_argument("--k", type=int, default=3, help="top-k")
    parser.add_argument("--M", type=int, default=8, help="max connections per layer")
    parser.add_argument("--ef", type=int, default=16, help="search candidate size (ef)")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--verbose", action="store_true", help="print step-by-step details (alias to DEBUG)")
    parser.add_argument("--plot-levels", action="store_true", help="visualize random level distribution after build")
    parser.add_argument("--plot-file", type=str, default="level_dist.png", help="output image file for level distribution")
    parser.add_argument("--show-plot", action="store_true", help="show the plot window (may block on headless env)")
    args = parser.parse_args()

    level = logging.getLevelName("DEBUG" if args.verbose else args.log_level)
    logger = setup_logger(level)

    logger.info(f"config dim={args.dim}, N={args.N}, Q={args.queries}, k={args.k}, M={args.M}, ef={args.ef}, seed={args.seed}")
    rng = np.random.default_rng(args.seed)
    xb = rng.random((args.N, args.dim), dtype=np.float32)
    xq = rng.random((args.queries, args.dim), dtype=np.float32)

    hnsw = HNSW(dim=args.dim, M=args.M, ef=args.ef, logger=logger, verbose=args.verbose)

    t0 = time.perf_counter()
    for i in range(args.N):
        hnsw.add(xb[i])
        if not args.verbose and (i + 1) % max(1, args.N // 10) == 0:
            logger.info(f"added {i+1}/{args.N}")
    t1 = time.perf_counter()

    # 简单统计：底层平均度
    if args.N > 0:
        deg0 = [len(hnsw.graph[i][0]) if len(hnsw.graph[i]) > 0 else 0 for i in range(len(hnsw.graph))]
        avg_deg0 = (sum(deg0) / len(deg0)) if deg0 else 0.0
    else:
        avg_deg0 = 0.0

    logger.info(f"build done: add_time={t1 - t0:.3f}s, avg_deg_level0={avg_deg0:.2f}, max_level={hnsw.max_level}, enter_point={hnsw.enter_point}")

    # 随机层分布可视化（可选）
    if args.plot_levels:
        plot_level_distribution(hnsw.levels, out_file=args.plot_file, show=args.show_plot, logger=logger)

    t2 = time.perf_counter()
    all_res = []
    for qi in range(args.queries):
        res = hnsw.search(xq[qi], k=args.k)
        all_res.append(res)
    t3 = time.perf_counter()
    avg_search_ms = ((t3 - t2) / max(1, args.queries)) * 1000.0
    logger.info(f"search done: total_time={t3 - t2:.3f}s, avg_per_query={avg_search_ms:.3f} ms, k={args.k}")

    # 打印前几个查询结果
    show = min(5, args.queries)
    for i in range(show):
        logger.info(f"Q{i} top{args.k} -> {all_res[i]}")

if __name__ == "__main__":
    main()
