import json
from pathlib import Path

import numpy as np
import pyvsag


def build_demo_index(dim: int, num_elements: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    vectors = rng.random((num_elements, dim), dtype=np.float32)
    ids = np.arange(num_elements, dtype=np.int64)

    index_params = json.dumps(
        {
            "dtype": "float32",
            "metric_type": "l2",
            "dim": dim,
            "hnsw": {
                "max_degree": 16,
                "ef_construction": 100,
            },
        }
    )

    index = pyvsag.Index("hnsw", index_params)
    index.build(
        vectors=vectors,
        ids=ids,
        num_elements=num_elements,
        dim=dim,
    )
    return index, vectors, ids, index_params


def run_once(index, query_vec: np.ndarray, top_k: int = 5, ef_search: int = 100):
    search_params = json.dumps({"hnsw": {"ef_search": ef_search}})
    result_ids, result_dists = index.knn_search(
        vector=query_vec,
        k=top_k,
        parameters=search_params,
    )
    return result_ids, result_dists


def main():
    dim = 128
    num_elements = 10_000
    index_path = Path("./vsag_hnsw_demo.index")

    index, vectors, ids, index_params = build_demo_index(dim=dim, num_elements=num_elements)

    query_id = 123
    query_vec = vectors[query_id]

    result_ids, result_dists = run_once(index, query_vec)
    print("[Before Save] query_id:", query_id)
    print("[Before Save] topk ids:", result_ids)
    print("[Before Save] topk dists:", result_dists)
    print("[Before Save] hit_self:", int(query_id in result_ids))

    file_sizes = index.save(str(index_path))
    print("Saved index:", index_path.resolve())
    print("Saved file sizes:", file_sizes)

    reloaded = pyvsag.Index("hnsw", index_params)
    reloaded.load(str(index_path))

    result_ids_2, result_dists_2 = run_once(reloaded, query_vec)
    print("[After Load] query_id:", query_id)
    print("[After Load] topk ids:", result_ids_2)
    print("[After Load] topk dists:", result_dists_2)
    print("[After Load] hit_self:", int(query_id in result_ids_2))


if __name__ == "__main__":
    main()
