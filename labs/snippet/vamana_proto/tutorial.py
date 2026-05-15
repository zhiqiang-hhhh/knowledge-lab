#!/usr/bin/env python3
"""
From basic graph search to Vamana-style indexing (dependency-free prototype).

This script is intentionally small and explicit. It demonstrates an evolution path:
1) exact linear scan
2) greedy hill-climbing on a graph
3) beam search on a graph (closer to ANN graph query)
4) graph pruning (RNG-style / NSG-like intuition)
5) simplified Vamana build loop with robust prune (alpha)
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from typing import Callable, List, Sequence, Set, Tuple

Vec = List[float]
Graph = List[List[int]]


def l2_sq(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) * (x - y) for x, y in zip(a, b))


def generate_clustered_data(n: int, d: int, n_clusters: int, seed: int) -> List[Vec]:
    rng = random.Random(seed)
    centers: List[Vec] = [[rng.uniform(-6.0, 6.0) for _ in range(d)] for _ in range(n_clusters)]
    data: List[Vec] = []
    for i in range(n):
        c = centers[i % n_clusters]
        data.append([c[j] + rng.gauss(0.0, 0.8) for j in range(d)])
    rng.shuffle(data)
    return data


def generate_queries_from_data(data: List[Vec], nq: int, noise_sigma: float, seed: int) -> List[Vec]:
    rng = random.Random(seed)
    queries: List[Vec] = []
    n = len(data)
    for _ in range(nq):
        base = data[rng.randrange(n)]
        queries.append([v + rng.gauss(0.0, noise_sigma) for v in base])
    return queries


def exact_topk(data: List[Vec], q: Vec, k: int) -> List[int]:
    pairs = [(l2_sq(q, x), i) for i, x in enumerate(data)]
    pairs.sort(key=lambda t: t[0])
    return [i for _, i in pairs[:k]]


def k_nn_graph(data: List[Vec], out_degree: int) -> Graph:
    n = len(data)
    g: Graph = [[] for _ in range(n)]
    for i in range(n):
        pairs = [(l2_sq(data[i], data[j]), j) for j in range(n) if j != i]
        pairs.sort(key=lambda t: t[0])
        g[i] = [j for _, j in pairs[:out_degree]]
    return g


def make_undirected(g: Graph, max_degree: int) -> Graph:
    n = len(g)
    ug: List[Set[int]] = [set(nei) for nei in g]
    for i in range(n):
        for j in g[i]:
            ug[j].add(i)
    out: Graph = []
    for i in range(n):
        nei = sorted(ug[i])
        if len(nei) > max_degree:
            nei = nei[:max_degree]
        out.append(nei)
    return out


def random_graph(n: int, out_degree: int, seed: int) -> Graph:
    rng = random.Random(seed)
    g: Graph = [[] for _ in range(n)]
    for i in range(n):
        candidates = list(range(n))
        candidates.remove(i)
        rng.shuffle(candidates)
        g[i] = candidates[:out_degree]
    return g


def greedy_search(
    data: List[Vec],
    g: Graph,
    q: Vec,
    entry: int,
    steps_limit: int = 10_000,
) -> Tuple[int, int]:
    """Hill-climbing: move to the best neighbor while distance improves."""
    cur = entry
    cur_d = l2_sq(q, data[cur])
    dcount = 1
    for _ in range(steps_limit):
        improved = False
        best = cur
        best_d = cur_d
        for nb in g[cur]:
            d = l2_sq(q, data[nb])
            dcount += 1
            if d < best_d:
                best_d = d
                best = nb
        if best != cur:
            cur = best
            cur_d = best_d
            improved = True
        if not improved:
            break
    return cur, dcount


def beam_search(
    data: List[Vec],
    g: Graph,
    q: Vec,
    entry: int,
    beam_width: int,
    visit_budget: int,
) -> Tuple[List[int], int]:
    """
    Best-first over graph frontier with bounded beam and visit budget.
    Roughly the query-time pattern used by modern graph ANN methods.
    """
    visited: Set[int] = set()
    # frontier keeps (distance, node), sorted ascending on each iteration (small N prototype)
    frontier: List[Tuple[float, int]] = [(l2_sq(q, data[entry]), entry)]
    dcount = 1
    visited.add(entry)
    results: List[Tuple[float, int]] = []

    while frontier and len(visited) < visit_budget:
        frontier.sort(key=lambda t: t[0])
        cur_d, cur = frontier.pop(0)
        results.append((cur_d, cur))
        for nb in g[cur]:
            if nb in visited:
                continue
            visited.add(nb)
            d = l2_sq(q, data[nb])
            dcount += 1
            frontier.append((d, nb))
        # Keep only top beam_width candidates in frontier.
        if len(frontier) > beam_width:
            frontier.sort(key=lambda t: t[0])
            frontier = frontier[:beam_width]

    results.sort(key=lambda t: t[0])
    return [i for _, i in results], dcount


def robust_prune(
    p: int,
    candidates: Sequence[int],
    data: List[Vec],
    max_degree: int,
    alpha: float,
) -> List[int]:
    """
    Vamana-style robust prune (simplified):
    - sort candidates by dist(p, x)
    - greedily keep x unless an already-kept y "covers" x:
      alpha * dist(x, y) <= dist(p, x)
    """
    cand = [c for c in set(candidates) if c != p]
    cand.sort(key=lambda x: l2_sq(data[p], data[x]))
    out: List[int] = []
    for x in cand:
        px = l2_sq(data[p], data[x])
        covered = False
        for y in out:
            if alpha * l2_sq(data[x], data[y]) <= px:
                covered = True
                break
        if not covered:
            out.append(x)
            if len(out) >= max_degree:
                break
    return out


def rng_style_prune(
    p: int,
    candidates: Sequence[int],
    data: List[Vec],
    max_degree: int,
) -> List[int]:
    """
    NSG/RNG-style intuition:
    keep x only if there is no selected y that is closer to x than p is to x.
    """
    cand = [c for c in set(candidates) if c != p]
    cand.sort(key=lambda x: l2_sq(data[p], data[x]))
    out: List[int] = []
    for x in cand:
        px = l2_sq(data[p], data[x])
        blocked = False
        for y in out:
            if l2_sq(data[x], data[y]) < px:
                blocked = True
                break
        if not blocked:
            out.append(x)
            if len(out) >= max_degree:
                break
    return out


def build_vamana_simplified(
    data: List[Vec],
    r: int,
    l_build: int,
    alpha: float,
    passes: int,
    seed: int,
) -> Graph:
    """
    Simplified Vamana build:
    1) random regular-ish init graph
    2) for each node p:
       - run beam search from a fixed entry to collect candidate set
       - union with existing out-neighbors
       - robust_prune -> new out-neighbors
       - add reverse edges with prune
    3) repeat passes for refinement
    """
    n = len(data)
    g = random_graph(n, r, seed)
    entry = 0
    for _ in range(passes):
        for p in range(n):
            found, _ = beam_search(
                data=data,
                g=g,
                q=data[p],
                entry=entry,
                beam_width=l_build,
                visit_budget=l_build * 4,
            )
            cand = set(found[: l_build * 2])
            cand.update(g[p])
            cand.discard(p)
            g[p] = robust_prune(p, list(cand), data, max_degree=r, alpha=alpha)

            # Add reverse links and keep degree bounded with the same prune rule.
            for nb in list(g[p]):
                rev_cand = set(g[nb])
                rev_cand.add(p)
                g[nb] = robust_prune(nb, list(rev_cand), data, max_degree=r, alpha=alpha)
    return g


def avg_out_degree(g: Graph) -> float:
    return sum(len(nei) for nei in g) / len(g)


@dataclass
class EvalResult:
    name: str
    recall_at_1: float
    avg_distance_computations: float


def evaluate_queries(
    data: List[Vec],
    queries: List[Vec],
    k: int,
    search_fn: Callable[[Vec], Tuple[List[int], int]],
    name: str,
) -> EvalResult:
    hit = 0
    dsum = 0
    for q in queries:
        gt = exact_topk(data, q, k)
        pred, dcount = search_fn(q)
        dsum += dcount
        if pred and pred[0] == gt[0]:
            hit += 1
    return EvalResult(name=name, recall_at_1=hit / len(queries), avg_distance_computations=dsum / len(queries))


def main() -> None:
    parser = argparse.ArgumentParser(description="Graph ANN evolution to Vamana (prototype)")
    parser.add_argument("--n", type=int, default=1200)
    parser.add_argument("--d", type=int, default=16)
    parser.add_argument("--nq", type=int, default=200)
    parser.add_argument("--clusters", type=int, default=24)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--knn-degree", type=int, default=24)
    parser.add_argument("--beam-width", type=int, default=32)
    parser.add_argument("--visit-budget", type=int, default=200)
    parser.add_argument("--r", type=int, default=24, help="target out-degree for pruned/vamana graph")
    parser.add_argument("--alpha", type=float, default=1.2, help="robust prune aggressiveness")
    parser.add_argument("--build-l", type=int, default=48, help="candidate breadth during Vamana build")
    parser.add_argument("--build-passes", type=int, default=2)
    args = parser.parse_args()

    data = generate_clustered_data(args.n, args.d, args.clusters, args.seed)
    queries = generate_queries_from_data(data, args.nq, noise_sigma=0.4, seed=args.seed + 7)
    entry = 0

    print("=== Dataset ===")
    print(
        f"N={args.n}, D={args.d}, NQ={args.nq}, clusters={args.clusters}, "
        f"knn_degree={args.knn_degree}, beam_width={args.beam_width}, visit_budget={args.visit_budget}"
    )

    # Stage A: Exact baseline.
    baseline = EvalResult(name="LinearScan(Exact)", recall_at_1=1.0, avg_distance_computations=float(args.n))

    # Stage B: Graph search on raw kNN graph.
    knn_g = make_undirected(k_nn_graph(data, args.knn_degree), max_degree=args.knn_degree * 2)

    def greedy_runner(q: Vec) -> Tuple[List[int], int]:
        node, dcount = greedy_search(data, knn_g, q, entry)
        return [node], dcount

    greedy_res = evaluate_queries(
        data,
        queries,
        args.k,
        greedy_runner,
        "GreedyOnKNNGraph",
    )
    beam_res_knn = evaluate_queries(
        data,
        queries,
        args.k,
        lambda q: beam_search(data, knn_g, q, entry, args.beam_width, args.visit_budget),
        "BeamOnKNNGraph",
    )

    # Stage C: NSG-like prune (diversification) from dense candidate graph.
    dense_g = k_nn_graph(data, out_degree=min(args.n - 1, args.knn_degree * 3))
    nsg_like: Graph = []
    for i in range(args.n):
        nsg_like.append(rng_style_prune(i, dense_g[i], data, max_degree=args.r))
    nsg_like = make_undirected(nsg_like, max_degree=args.r * 2)
    beam_res_nsg_like = evaluate_queries(
        data,
        queries,
        args.k,
        lambda q: beam_search(data, nsg_like, q, entry, args.beam_width, args.visit_budget),
        "BeamOnNSGStyleGraph",
    )

    # Stage D: Simplified Vamana build + beam query.
    vamana_g = build_vamana_simplified(
        data=data,
        r=args.r,
        l_build=args.build_l,
        alpha=args.alpha,
        passes=args.build_passes,
        seed=args.seed,
    )
    beam_res_vamana = evaluate_queries(
        data,
        queries,
        args.k,
        lambda q: beam_search(data, vamana_g, q, entry, args.beam_width, args.visit_budget),
        "BeamOnVamanaStyleGraph",
    )

    print("\n=== Results (higher recall better, lower distance computations better) ===")
    for r in [baseline, greedy_res, beam_res_knn, beam_res_nsg_like, beam_res_vamana]:
        print(
            f"{r.name:24s} recall@1={r.recall_at_1:.4f} "
            f"avg_dist_computations={r.avg_distance_computations:.1f}"
        )

    print("\n=== Graph Stats ===")
    print(f"kNN graph avg degree:          {avg_out_degree(knn_g):.2f}")
    print(f"NSG-style graph avg degree:    {avg_out_degree(nsg_like):.2f}")
    print(f"Vamana-style graph avg degree: {avg_out_degree(vamana_g):.2f}")

    print("\n=== Interpretation Guide ===")
    print("1) Greedy can get stuck at local minima; beam search is usually stronger.")
    print("2) Pruning keeps graph sparse while preserving navigability.")
    print("3) Robust prune (alpha) controls diversity vs. locality in Vamana.")
    print("4) Vamana-like build tries to improve global routing quality, not only local kNN links.")


if __name__ == "__main__":
    main()
