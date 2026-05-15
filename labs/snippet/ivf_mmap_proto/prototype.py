#!/usr/bin/env python3
"""
Minimal IVF + mmap prototype.

Goals:
1) Show IVF principle: probe only a few coarse clusters (`nprobe`) instead of full scan.
2) Show mmap principle: vectors are stored on disk and read on demand from probed list ranges.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class IVFIndexMeta:
    d: int
    nlist: int
    offsets: np.ndarray  # shape [nlist + 1], int64
    centroids: np.ndarray  # shape [nlist, d], float32


def l2_sq_batch_to_centroids(x: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    # (N, D) to (K, D) -> (N, K)
    return np.sum((x[:, None, :] - centroids[None, :, :]) ** 2, axis=2)


def simple_kmeans(x: np.ndarray, k: int, iters: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n, _ = x.shape
    init_idx = rng.choice(n, size=k, replace=False)
    centroids = x[init_idx].copy()

    for _ in range(iters):
        d2 = l2_sq_batch_to_centroids(x, centroids)
        assign = np.argmin(d2, axis=1)
        new_centroids = centroids.copy()
        for i in range(k):
            members = x[assign == i]
            if len(members) == 0:
                new_centroids[i] = x[rng.integers(0, n)]
            else:
                new_centroids[i] = members.mean(axis=0)
        centroids = new_centroids
    return centroids.astype(np.float32, copy=False)


def build_ivf_ondisk(
    xb: np.ndarray,
    out_dir: Path,
    nlist: int,
    kmeans_iters: int,
    seed: int,
) -> IVFIndexMeta:
    out_dir.mkdir(parents=True, exist_ok=True)
    n, d = xb.shape

    centroids = simple_kmeans(xb, k=nlist, iters=kmeans_iters, seed=seed)
    coarse_d2 = l2_sq_batch_to_centroids(xb, centroids)
    list_ids = np.argmin(coarse_d2, axis=1)

    # Group vectors by list id so each inverted list is a contiguous on-disk range.
    order = np.argsort(list_ids, kind="stable")
    sorted_list_ids = list_ids[order]
    counts = np.bincount(sorted_list_ids, minlength=nlist).astype(np.int64)
    offsets = np.zeros(nlist + 1, dtype=np.int64)
    offsets[1:] = np.cumsum(counts)

    xb_sorted = xb[order]
    ids_sorted = order.astype(np.int32)

    (out_dir / "vectors.f32").write_bytes(xb_sorted.astype(np.float32, copy=False).tobytes())
    (out_dir / "ids.i32").write_bytes(ids_sorted.tobytes())
    np.savez(
        out_dir / "meta.npz",
        d=np.int32(d),
        nlist=np.int32(nlist),
        offsets=offsets,
        centroids=centroids.astype(np.float32, copy=False),
    )
    return IVFIndexMeta(d=d, nlist=nlist, offsets=offsets, centroids=centroids)


def load_ivf_ondisk(index_dir: Path) -> tuple[IVFIndexMeta, np.memmap, np.memmap]:
    meta = np.load(index_dir / "meta.npz")
    d = int(meta["d"])
    nlist = int(meta["nlist"])
    offsets = meta["offsets"].astype(np.int64, copy=False)
    centroids = meta["centroids"].astype(np.float32, copy=False)
    n = int(offsets[-1])

    vectors_mm = np.memmap(index_dir / "vectors.f32", dtype=np.float32, mode="r", shape=(n, d))
    ids_mm = np.memmap(index_dir / "ids.i32", dtype=np.int32, mode="r", shape=(n,))
    return IVFIndexMeta(d=d, nlist=nlist, offsets=offsets, centroids=centroids), vectors_mm, ids_mm


def brute_force_topk(xb: np.ndarray, q: np.ndarray, k: int) -> np.ndarray:
    d2 = np.sum((xb - q[None, :]) ** 2, axis=1)
    idx = np.argpartition(d2, kth=k - 1)[:k]
    return idx[np.argsort(d2[idx])]


def ivf_search_one(
    q: np.ndarray,
    meta: IVFIndexMeta,
    vectors_mm: np.memmap,
    ids_mm: np.memmap,
    nprobe: int,
    k: int,
) -> tuple[np.ndarray, int]:
    coarse_d2 = np.sum((meta.centroids - q[None, :]) ** 2, axis=1)
    probe = np.argpartition(coarse_d2, kth=nprobe - 1)[:nprobe]

    cand_ids = []
    cand_d2 = []
    cand_cnt = 0
    for lid in probe:
        start = int(meta.offsets[lid])
        end = int(meta.offsets[lid + 1])
        if start == end:
            continue
        chunk = vectors_mm[start:end]  # mmap-backed read for only this list range
        d2 = np.sum((chunk - q[None, :]) ** 2, axis=1)
        cand_d2.append(d2)
        cand_ids.append(np.asarray(ids_mm[start:end], dtype=np.int32))
        cand_cnt += end - start

    if cand_cnt == 0:
        return np.empty((0,), dtype=np.int32), 0
    all_d2 = np.concatenate(cand_d2)
    all_ids = np.concatenate(cand_ids)
    top = min(k, len(all_d2))
    idx = np.argpartition(all_d2, kth=top - 1)[:top]
    idx = idx[np.argsort(all_d2[idx])]
    return all_ids[idx], cand_cnt


def recall_at_k(gt: np.ndarray, pred: np.ndarray) -> float:
    if len(gt) == 0:
        return 0.0
    return len(set(gt.tolist()) & set(pred.tolist())) / len(gt)


def main() -> None:
    parser = argparse.ArgumentParser(description="IVF + mmap prototype")
    parser.add_argument("--workdir", type=Path, default=Path("ivf_mmap_proto/data"))
    parser.add_argument("--n", type=int, default=50000, help="number of base vectors")
    parser.add_argument("--d", type=int, default=64, help="vector dimension")
    parser.add_argument("--nq", type=int, default=100, help="number of queries")
    parser.add_argument("--nlist", type=int, default=128, help="number of IVF lists")
    parser.add_argument("--nprobe", type=int, default=8, help="number of probed lists")
    parser.add_argument("--k", type=int, default=10, help="top-k")
    parser.add_argument("--kmeans-iters", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    xb = rng.normal(0.0, 1.0, size=(args.n, args.d)).astype(np.float32)
    xq = rng.normal(0.0, 1.0, size=(args.nq, args.d)).astype(np.float32)

    t0 = time.perf_counter()
    meta = build_ivf_ondisk(
        xb=xb,
        out_dir=args.workdir,
        nlist=args.nlist,
        kmeans_iters=args.kmeans_iters,
        seed=args.seed,
    )
    t1 = time.perf_counter()
    meta, vectors_mm, ids_mm = load_ivf_ondisk(args.workdir)
    t2 = time.perf_counter()

    recalls = []
    total_cands = 0
    ivf_t0 = time.perf_counter()
    for q in xq:
        gt = brute_force_topk(xb, q, args.k)
        pred, cand_cnt = ivf_search_one(
            q=q, meta=meta, vectors_mm=vectors_mm, ids_mm=ids_mm, nprobe=args.nprobe, k=args.k
        )
        recalls.append(recall_at_k(gt, pred))
        total_cands += cand_cnt
    ivf_t1 = time.perf_counter()

    avg_cands = total_cands / args.nq
    cand_ratio = avg_cands / args.n
    bytes_per_vec = args.d * 4
    estimated_bytes_per_query = avg_cands * bytes_per_vec

    print("=== IVF + mmap prototype ===")
    print(f"N={args.n}, D={args.d}, NQ={args.nq}, nlist={args.nlist}, nprobe={args.nprobe}, k={args.k}")
    print(f"build_index_time={t1 - t0:.3f}s, load_mmap_time={t2 - t1:.3f}s")
    print(f"search_time={ivf_t1 - ivf_t0:.3f}s, qps={args.nq / (ivf_t1 - ivf_t0):.2f}")
    print(f"avg_recall@{args.k}={np.mean(recalls):.4f}")
    print(f"avg_candidates={avg_cands:.1f}/{args.n} ({cand_ratio:.2%} of full scan)")
    print(
        "estimated_vec_bytes_read_per_query="
        f"{estimated_bytes_per_query / (1024 * 1024):.2f} MiB "
        f"(full scan would be {(args.n * bytes_per_vec) / (1024 * 1024):.2f} MiB)"
    )
    print()
    print("Interpretation:")
    print("1) IVF: only nprobe lists are scanned, so candidates << N.")
    print("2) mmap: vectors stay on disk; query touches only selected list ranges.")
    print("3) Increase nprobe -> higher recall, but more candidates/I-O.")


if __name__ == "__main__":
    main()
