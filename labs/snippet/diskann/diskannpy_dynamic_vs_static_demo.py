import os
from pathlib import Path

import numpy as np

import diskannpy as dap


def build_and_use_dynamic_memory_index(base_dir: Path) -> None:
    # Dynamic memory index: mutable (insert/delete), in-memory.
    dim = 64
    n = 2000
    extra_capacity = 500
    rng = np.random.default_rng(42)

    vectors = rng.random((n, dim), dtype=np.float32)
    ids = np.arange(n, dtype=np.uint32)
    queries = rng.random((5, dim), dtype=np.float32)

    index = dap.DynamicMemoryIndex(
        distance_metric="l2",
        vector_dtype=np.float32,
        dimensions=dim,
        max_vectors=n + extra_capacity,
        complexity=100,
        graph_degree=64,
        num_threads=0,
    )

    index.batch_insert(vectors, ids, num_threads=0)

    result = index.batch_search(
        queries=queries,
        k_neighbors=5,
        complexity=50,
        num_threads=0,
    )

    print("dynamic memory search identifiers:", result.identifiers[:2])

    # Persist and reload.
    save_dir = base_dir / "dynamic_index"
    save_dir.mkdir(parents=True, exist_ok=True)
    index.save(str(save_dir), index_prefix="dyn")

    reloaded = dap.DynamicMemoryIndex.from_file(
        index_directory=str(save_dir),
        max_vectors=n + extra_capacity,
        complexity=100,
        graph_degree=64,
        distance_metric="l2",
        vector_dtype=np.float32,
        dimensions=dim,
        index_prefix="dyn",
    )

    result = reloaded.batch_search(
        queries=queries,
        k_neighbors=5,
        complexity=50,
        num_threads=0,
    )
    print("reloaded dynamic search identifiers:", result.identifiers[:2])


def build_and_use_static_disk_index(base_dir: Path) -> None:
    # Static disk index: immutable, disk-backed.
    dim = 64
    n = 5000
    rng = np.random.default_rng(7)

    vectors = rng.random((n, dim), dtype=np.float32)
    queries = rng.random((3, dim), dtype=np.float32)

    index_dir = base_dir / "static_disk_index"
    index_dir.mkdir(parents=True, exist_ok=True)

    # Build a static disk index from in-memory vectors.
    dap.build_disk_index(
        data=vectors,
        distance_metric="l2",
        index_directory=str(index_dir),
        complexity=100,
        graph_degree=64,
        search_memory_maximum=0.5,
        build_memory_maximum=1.0,
        num_threads=0,
        pq_disk_bytes=0,
        vector_dtype=np.float32,
        index_prefix="disk",
    )

    disk_index = dap.StaticDiskIndex(
        index_directory=str(index_dir),
        num_threads=0,
        num_nodes_to_cache=1000,
        cache_mechanism=1,
        distance_metric="l2",
        vector_dtype=np.float32,
        dimensions=dim,
        index_prefix="disk",
    )

    # Static disk index exposes search APIs only (no insert/delete).
    result = disk_index.batch_search(
        queries=queries,
        k_neighbors=5,
        complexity=50,
        num_threads=0,
        beam_width=2,
    )

    print("static disk search identifiers:", result.identifiers[:2])


def main() -> None:
    base_dir = Path(os.environ.get("DISKANN_DEMO_DIR", "./diskann_demo_out"))
    base_dir.mkdir(parents=True, exist_ok=True)

    build_and_use_dynamic_memory_index(base_dir)
    build_and_use_static_disk_index(base_dir)


if __name__ == "__main__":
    main()
