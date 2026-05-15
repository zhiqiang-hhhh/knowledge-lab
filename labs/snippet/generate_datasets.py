#!/usr/bin/env python3
"""
Generate 4 user-partitioned vector embedding datasets from SIFT 1M source data.
Optimized version with multiprocessing and batch I/O.

Datasets:
  - dataset_1w:   100 users x 10,000 vectors   = 1M total
  - dataset_10w:  100 users x 100,000 vectors   = 10M total
  - dataset_50w:  100 users x 500,000 vectors   = 50M total
  - dataset_100w: 100 users x 1,000,000 vectors = 100M total

Output format: TSV (tab-separated), gzip compressed, sharded by ~1M rows.
Columns: user_id<TAB>id<TAB>[v1,v2,...,v128]
"""

import gzip
import os
import sys
import time
import numpy as np
from multiprocessing import Pool, shared_memory
import json

# Configuration
SOURCE_FILE = "datasets/source/sift_database.tsv"
OUTPUT_BASE = "datasets"
NUM_USERS = 100
SHARD_SIZE = 1_000_000  # rows per shard
SEED = 42
WRITE_CHUNK = 50_000    # lines to batch before writing
NUM_WORKERS = 32        # parallel workers
COMPRESS_LEVEL = 1      # fast compression

DATASETS = [
    ("dataset_1w",   10_000),
    ("dataset_10w",  100_000),
    ("dataset_50w",  500_000),
    ("dataset_100w", 1_000_000),
]


def load_source_embeddings(filepath):
    """Load all embedding strings from the source TSV file."""
    print(f"Loading source data from {filepath}...")
    t0 = time.time()
    embeddings = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                embeddings.append(parts[1])
    elapsed = time.time() - t0
    print(f"Loaded {len(embeddings)} embeddings in {elapsed:.1f}s")
    return embeddings


def generate_shard(args):
    """Worker function: generate one shard file.

    Each shard contains data for a contiguous group of users.
    Uses fork-inherited global `EMBEDDINGS` list (copy-on-write, no pickling).
    """
    shard_idx, user_ids, vectors_per_user, output_dir, base_seed = args
    source_size = len(EMBEDDINGS)
    shard_path = os.path.join(output_dir, f"shard_{shard_idx:03d}.tsv.gz")
    total_written = 0

    with gzip.open(shard_path, "wb", compresslevel=COMPRESS_LEVEL) as fout:
        for user_id in user_ids:
            # Deterministic seed per user for reproducibility
            rng = np.random.default_rng(base_seed + user_id)
            indices = rng.integers(0, source_size, size=vectors_per_user)

            # Write in chunks to balance memory usage and I/O efficiency
            for chunk_start in range(0, vectors_per_user, WRITE_CHUNK):
                chunk_end = min(chunk_start + WRITE_CHUNK, vectors_per_user)
                chunk_indices = indices[chunk_start:chunk_end]

                lines = []
                for i, idx in enumerate(chunk_indices, start=chunk_start):
                    lines.append(f"{user_id}\t{i}\t{EMBEDDINGS[idx]}")
                chunk_bytes = ("\n".join(lines) + "\n").encode("ascii")
                fout.write(chunk_bytes)
                total_written += len(chunk_indices)

    file_size = os.path.getsize(shard_path)
    return shard_idx, total_written, file_size


def generate_dataset(embeddings, dataset_name, vectors_per_user):
    """Generate a dataset using multiprocessing across shards."""
    total_rows = NUM_USERS * vectors_per_user
    output_dir = os.path.join(OUTPUT_BASE, dataset_name)
    os.makedirs(output_dir, exist_ok=True)

    # Determine how to group users into shards
    # Each shard should have ~SHARD_SIZE rows
    users_per_shard = max(1, SHARD_SIZE // vectors_per_user)
    shard_tasks = []
    shard_idx = 0
    for start_user in range(0, NUM_USERS, users_per_shard):
        end_user = min(start_user + users_per_shard, NUM_USERS)
        user_ids = list(range(start_user, end_user))
        shard_tasks.append((shard_idx, user_ids, vectors_per_user, output_dir, SEED))
        shard_idx += 1

    num_shards = len(shard_tasks)
    workers = min(NUM_WORKERS, num_shards)

    print(f"\n{'='*60}")
    print(f"Generating {dataset_name}: {NUM_USERS} users x {vectors_per_user:,} vectors = {total_rows:,} rows")
    print(f"  Shards: {num_shards} ({users_per_shard} users/shard, ~{users_per_shard * vectors_per_user:,} rows/shard)")
    print(f"  Workers: {workers}")
    print(f"  Output: {output_dir}/")
    print(f"{'='*60}")

    t0 = time.time()
    total_written = 0
    total_size = 0

    with Pool(processes=workers) as pool:
        for result in pool.imap_unordered(generate_shard, shard_tasks):
            s_idx, s_rows, s_size = result
            total_written += s_rows
            total_size += s_size
            elapsed = time.time() - t0
            pct = total_written / total_rows * 100
            speed = total_written / elapsed if elapsed > 0 else 0
            print(f"  Shard {s_idx:03d} done | "
                  f"Progress: {total_written:>12,}/{total_rows:,} ({pct:5.1f}%) | "
                  f"Elapsed: {elapsed:7.1f}s | "
                  f"Speed: {speed:,.0f} rows/s")

    elapsed = time.time() - t0
    print(f"\n  Done! {total_written:,} rows in {elapsed:.1f}s")
    print(f"  Total compressed size: {total_size / (1024**3):.2f} GB ({num_shards} shards)")
    return total_written


# Global variable for fork-inherited sharing with workers
EMBEDDINGS = []


def main():
    global EMBEDDINGS

    target = sys.argv[1] if len(sys.argv) > 1 else None

    EMBEDDINGS = load_source_embeddings(SOURCE_FILE)

    for dataset_name, vectors_per_user in DATASETS:
        if target and dataset_name != target:
            continue
        generate_dataset(EMBEDDINGS, dataset_name, vectors_per_user)

    print("\nAll done!")


if __name__ == "__main__":
    main()
