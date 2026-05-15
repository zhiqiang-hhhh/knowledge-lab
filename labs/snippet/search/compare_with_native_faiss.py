import faiss
import numpy as np
import logging
import os
import random
from query import get_conn
import mysql.connector
from typing import List, Tuple, Set, Optional, Dict, Any
import math
import matplotlib.pyplot as plt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def read_tsv_data(file_path: str) -> Tuple[np.ndarray, np.ndarray]:
    """Read data from a TSV file and return IDs and embeddings.

    If file_path is a directory, randomly pick one .tsv chunk inside and load only that chunk.
    """
    ids = []
    embeddings = []

    # Determine which TSV to read
    if os.path.isdir(file_path):
        candidates = [os.path.join(file_path, f) for f in os.listdir(file_path) if f.endswith('.tsv')]
        if not candidates:
            raise FileNotFoundError(f"No .tsv files found in directory: {file_path}")
        chosen = random.choice(candidates)
        logger.info(f"Randomly selected chunk: {os.path.basename(chosen)} from {file_path}")
        tsv_to_read = chosen
        # Only read the head (first 100 lines) of the chosen chunk file
        max_lines = 100
        with open(tsv_to_read, "r") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    ids.append(int(parts[0]))
                    vector = np.array([float(x) for x in parts[2].strip('[]').split(',')], dtype=np.float32)
                    embeddings.append(vector)
        return np.array(ids, dtype=np.int64), np.array(embeddings, dtype=np.float32)
    elif os.path.isfile(file_path):
        tsv_to_read = file_path
        # Read the whole file (original behavior)
        with open(tsv_to_read, "r") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    ids.append(int(parts[0]))
                    vector = np.array([float(x) for x in parts[2].strip('[]').split(',')], dtype=np.float32)
                    embeddings.append(vector)
        return np.array(ids, dtype=np.int64), np.array(embeddings, dtype=np.float32)
    else:
        raise ValueError(f"Invalid file_path: {file_path}")

def get_table_tsv_files(data_dir: str, table: str) -> List[str]:
    """Return a list of TSV files for the given table.
    Prefer a single {table}.tsv if it exists; otherwise collect all {table}_chunk_*.tsv files.
    """
    single = os.path.join(data_dir, f"{table}.tsv")
    if os.path.exists(single):
        return [single]
    # collect chunk files and sort by chunk index if present
    candidates = [
        os.path.join(data_dir, f)
        for f in os.listdir(data_dir)
        if f.startswith(f"{table}_chunk_") and f.endswith(".tsv")
    ]
    def _chunk_key(p: str) -> int:
        name = os.path.basename(p)
        try:
            return int(name.split("_chunk_")[-1].split(".")[0])
        except Exception:
            return 1<<30
    return sorted(candidates, key=_chunk_key)

def build_faiss_index_from_tsv_files(
    files: List[str],
    index_type: str,
    metric_type: str,
    dimension: int,
    batch_size: int = 50000,
    sample_size: int = 200000,
) -> Tuple[faiss.IndexIDMap, np.ndarray, np.ndarray]:
    """Build a FAISS index by streaming through TSV files without loading everything into memory.

    Returns: (index, sample_ids, sample_embeddings) where sample_* are a small subset used for radius estimation.
    """
    # create base index
    if metric_type.lower() in ["l2", "l2 distance"]:
        metric = faiss.METRIC_L2
    elif metric_type.lower() in ["ip", "inner product"]:
        metric = faiss.METRIC_INNER_PRODUCT
    else:
        raise ValueError(f"Unsupported metric_type: {metric_type}")

    if index_type.lower() == "flat":
        base_index = faiss.IndexFlat(dimension, metric)
    elif index_type.lower() == "hnsw":
        base_index = faiss.IndexHNSWFlat(dimension, 32, metric)
    else:
        raise ValueError(f"Unsupported index_type: {index_type}")

    index = faiss.IndexIDMap(base_index)

    ids_batch: List[int] = []
    vecs_batch: List[List[float]] = []
    sample_ids: List[int] = []
    sample_vecs: List[List[float]] = []

    for fp in files:
        logger.info(f"Indexing file: {os.path.basename(fp)}")
        with open(fp, "r") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                try:
                    vid = int(parts[0])
                    vec = [float(x) for x in parts[2].strip('[]').split(',')]
                except Exception:
                    continue
                ids_batch.append(vid)
                vecs_batch.append(vec)

                # simple head sampling up to sample_size
                if len(sample_ids) < sample_size:
                    sample_ids.append(vid)
                    sample_vecs.append(vec)

                if len(ids_batch) >= batch_size:
                    index.add_with_ids(np.asarray(vecs_batch, dtype=np.float32), np.asarray(ids_batch, dtype=np.int64))
                    ids_batch.clear()
                    vecs_batch.clear()

        # flush remaining per file as well (optional, handled after loop too)
        if ids_batch:
            index.add_with_ids(np.asarray(vecs_batch, dtype=np.float32), np.asarray(ids_batch, dtype=np.int64))
            ids_batch.clear()
            vecs_batch.clear()

    # finalize sample arrays
    sample_ids_arr = np.asarray(sample_ids, dtype=np.int64)
    sample_vecs_arr = np.asarray(sample_vecs, dtype=np.float32)
    logger.info(f"Finished building index. Total sample size: {len(sample_ids_arr)}")
    return index, sample_ids_arr, sample_vecs_arr

def build_faiss_index(index_type: str, metric_type: str, embeddings: np.ndarray, ids: np.ndarray, dimension: int) -> faiss.IndexIDMap:
    """
    Build a Faiss index from embeddings with explicit IDs.
    index_type: "flat" or "hnsw"
    metric_type: "l2" or "ip"
    """
    # Select metric
    if metric_type.lower() in ["l2", "l2 distance"]:
        metric = faiss.METRIC_L2
    elif metric_type.lower() in ["ip", "inner product"]:
        metric = faiss.METRIC_INNER_PRODUCT
    else:
        raise ValueError(f"Unsupported metric_type: {metric_type}")

    # Select index type
    if index_type.lower() == "flat":
        index = faiss.IndexFlat(dimension, metric)
    elif index_type.lower() == "hnsw":
        index = faiss.IndexHNSWFlat(dimension, 32, metric)
    else:
        raise ValueError(f"Unsupported index_type: {index_type}")

    # Add the ID mapping layer
    id_map = faiss.IndexIDMap(index)

    # Add vectors with their IDs
    id_map.add_with_ids(embeddings, ids)

    return id_map

def faiss_range_search(index: faiss.IndexIDMap, query_vector: np.ndarray, radius: float) -> List[Tuple[int, float]]:
    """Perform range search with Faiss native range_search API"""
    # For Faiss, the radius needs to be squared since it works with squared distances
    squared_radius = radius * radius
    
    # Reshape to ensure query_vector is 2D
    query_vector_reshaped = np.array([query_vector], dtype=np.float32)
    
    # Perform range search - returns distances and indices for points within radius
    lims, D, I = index.range_search(query_vector_reshaped, squared_radius)
    
    # Process results
    results = []
    # We only have one query, so results are from lims[0] to lims[1]
    for i in range(int(lims[0]), int(lims[1])):
        # Apply square root to convert from squared distance to actual distance
        results.append((int(I[i]), math.sqrt(float(D[i]))))
    
    # Sort by distance
    results.sort(key=lambda x: x[1])
    return results

def faiss_range_search_greater(index: faiss.IndexIDMap, query_vector: np.ndarray, radius: float, all_ids: Optional[np.ndarray] = None) -> List[Tuple[int, float]]:
    """
    Perform range search with Faiss for distances greater than radius
    by finding the set difference between all IDs and IDs with distance < radius
    """
    # For Faiss, the radius needs to be squared since it works with squared distances
    squared_radius = radius * radius
    
    # Reshape to ensure query_vector is 2D
    query_vector_reshaped = np.array([query_vector], dtype=np.float32)
    
    # Get all IDs with distance < radius
    lims, D, I = index.range_search(query_vector_reshaped, squared_radius)
    
    # Create a set of IDs with distance < radius
    ids_within_radius = set()
    for i in range(int(lims[0]), int(lims[1])):
        ids_within_radius.add(int(I[i]))
    
    # IDs with distance > radius are the set difference between all_ids and ids_within_radius
    ids_beyond_radius = set(all_ids) - ids_within_radius
    
    # Create a list to store the results
    results = []
    
    # If we have no IDs beyond the radius, return empty results
    if not ids_beyond_radius:
        return results
    
    # We need to get distances for IDs with distance > radius
    # Use regular search for a large number of results
    large_k = min(1000, len(all_ids))  # Use a large k to get most vectors
    D, I = index.search(query_vector_reshaped, large_k)
    
    # Create a mapping from ID to distance
    id_to_dist = {}
    for i in range(len(I[0])):
        if I[0][i] != -1:
            # Apply square root to convert from squared distance to actual distance
            id_to_dist[int(I[0][i])] = math.sqrt(float(D[0][i]))
    
    # Add IDs beyond radius with their distances to results
    for id_val in ids_beyond_radius:
        if id_val in id_to_dist:
            results.append((id_val, id_to_dist[id_val]))
    
    # Sort by distance
    results.sort(key=lambda x: x[1])
    return results

def faiss_topn_search(index: faiss.IndexIDMap, query_vector: np.ndarray, limit: int = 5) -> List[Tuple[int, float]]:
    """Perform top-N search with Faiss"""
    D, I = index.search(np.array([query_vector]), limit)
    results = []
    
    for i in range(min(len(I[0]), limit)):
        if I[0][i] != -1:  # Skip invalid results
            # Apply square root to convert from squared distance to actual distance
            results.append((int(I[0][i]), math.sqrt(float(D[0][i]))))
    
    return results

def faiss_compound_search(index: faiss.IndexIDMap, query_vector: np.ndarray, radius: float, limit: int = 5) -> List[Tuple[int, float]]:
    """Perform compound search with Faiss"""
    # For Faiss, the radius needs to be squared since it works with squared distances
    squared_radius = radius * radius
    
    # Reshape to ensure query_vector is 2D
    query_vector_reshaped = np.array([query_vector], dtype=np.float32)
    
    # Step 1: Perform range search to get IDs within radius
    lims, D, I = index.range_search(query_vector_reshaped, squared_radius)
    
    # If no results found within radius, return empty list
    if lims[1] == lims[0]:
        return []
    
    # Step 2: Create an IdSelectorBatch with numpy array of int64
    range_ids = np.array([int(I[i]) for i in range(int(lims[0]), int(lims[1]))], dtype=np.int64)
    logger.info(f"Range search found {len(range_ids)} IDs within radius")

    id_selector = faiss.IDSelectorBatch(range_ids)
    
    # Step 3: Perform top-K search with the ID selector to filter results
    # The limit parameter is used directly as K for the top-K search
    params = faiss.SearchParametersHNSW()
    params.sel = id_selector
    D_topn, I_topn = index.search(query_vector_reshaped, limit, params=params)
    logger.info(f"Top-N search found {len(I_topn[0])} IDs")
    # Process the results
    results = []
    for i in range(len(I_topn[0])):
        if I_topn[0][i] != -1:  # Skip invalid results
            # Apply square root to convert from squared distance to actual distance
            results.append((int(I_topn[0][i]), math.sqrt(float(D_topn[0][i]))))
    
    return results

def get_radius(query_vector: np.ndarray, embeddings: np.ndarray, percentile: int) -> float:
    """
    Calculate the radius based on a percentile of distances from query_vector to all embeddings
    
    Args:
        query_vector: The query vector
        embeddings: All embedding vectors
        percentile: The percentile (0-100) to use for radius calculation
    
    Returns:
        The distance value at the specified percentile
    """
    # Calculate L2 distances from query vector to all embeddings (vectorized)
    distances = np.sqrt(np.sum((embeddings - query_vector) ** 2, axis=1))
    
    # Return the specified percentile
    return float(np.percentile(distances, percentile))

# _table_metrics 结构说明:
# {
#     table_name: {
#         test_name: {
#             "doris_precision": float,   # Doris结果的precision（命中ground truth的比例，0~1）
#             "doris_recall": float,      # Doris结果的recall（ground truth被命中的比例，0~1）
#             "overlap": float,           # Doris与FAISS结果ID的重叠比例（交集/FAISS结果数，0~1）
#         },
#         ...
#     },
#     ...
# }
_table_metrics = {}

def compute_overlap(faiss_results: List[Tuple[int, float]], doris_results: List[Tuple], distance_tolerance: float = 1e-3) -> float:
    """计算重合率（ID和距离都匹配的结果数/FAISS结果数）"""
    if not faiss_results:
        return 0.0
    
    # 创建字典便于快速查找 {id: distance}
    faiss_dict = {result[0]: result[1] for result in faiss_results}
    doris_dict = {int(result[0]): float(result[1]) for result in doris_results}
    
    matched_count = 0
    for faiss_id, faiss_dist in faiss_dict.items():
        if faiss_id in doris_dict:
            doris_dist = doris_dict[faiss_id]
            # 检查距离是否在容差范围内相等
            if abs(faiss_dist - doris_dist) <= distance_tolerance:
                matched_count += 1
    
    return matched_count / len(faiss_results)

def compute_precision(doris_results: List[Tuple], ground_truth_results: List[Tuple[int, float]], distance_tolerance: float = 1e-3) -> float:
    """计算正确率（Doris命中ground truth且距离匹配的比例）"""
    if not doris_results:
        return 0.0
    
    # 创建字典便于快速查找 {id: distance}
    gt_dict = {result[0]: result[1] for result in ground_truth_results}
    
    matched_count = 0
    for doris_result in doris_results:
        doris_id = int(doris_result[0])
        doris_dist = float(doris_result[1])
        
        if doris_id in gt_dict:
            gt_dist = gt_dict[doris_id]
            # 检查距离是否在容差范围内相等
            if abs(doris_dist - gt_dist) <= distance_tolerance:
                matched_count += 1
    
    return matched_count / len(doris_results)

def compute_recall(doris_results: List[Tuple], ground_truth_results: List[Tuple[int, float]], distance_tolerance: float = 1e-3) -> float:
    """计算召回率（ground truth被Doris命中且距离匹配的比例）"""
    if not ground_truth_results:
        return 0.0
    
    # 创建字典便于快速查找 {id: distance}
    doris_dict = {int(result[0]): float(result[1]) for result in doris_results}
    
    matched_count = 0
    for gt_id, gt_dist in ground_truth_results:
        if gt_id in doris_dict:
            doris_dist = doris_dict[gt_id]
            # 检查距离是否在容差范围内相等
            if abs(doris_dist - gt_dist) <= distance_tolerance:
                matched_count += 1
    
    return matched_count / len(ground_truth_results)

def compare_and_log(
    faiss_results: List[Tuple[int, float]],
    doris_results: List[Tuple],
    test_name: str,
    dimension: int = 0,
    table_name: str = None,
    ground_truth: Optional[List[Tuple[int, float]]] = None,
    distance_tolerance: float = 1e-3
):
    """输出精度、召回率、重叠比例（基于ID和距离的匹配）"""
    # 使用新的比较函数，考虑距离值
    overlap = compute_overlap(faiss_results, doris_results, distance_tolerance)

    doris_precision = doris_recall = faiss_precision = faiss_recall = None
    if ground_truth is not None:
        doris_precision = compute_precision(doris_results, ground_truth, distance_tolerance)
        doris_recall = compute_recall(doris_results, ground_truth, distance_tolerance)
        faiss_precision = compute_precision([(r[0], r[1]) for r in faiss_results], ground_truth, distance_tolerance)
        faiss_recall = compute_recall([(r[0], r[1]) for r in faiss_results], ground_truth, distance_tolerance)

    # 打印 precision/recall/overlap
    logger.info(f"[{test_name}] Overlap (ID+Distance): {overlap*100:.2f}%")
    if ground_truth is not None:
        logger.info(f"[{test_name}] Doris Precision (ID+Distance): {doris_precision*100:.2f}%")
        logger.info(f"[{test_name}] Doris Recall (ID+Distance): {doris_recall*100:.2f}%")
        logger.info(f"[{test_name}] Faiss Precision (ID+Distance): {faiss_precision*100:.2f}%")
        logger.info(f"[{test_name}] Faiss Recall (ID+Distance): {faiss_recall*100:.2f}%")
    else:
        logger.info(f"[{test_name}] Precision: N/A (no ground truth)")
        logger.info(f"[{test_name}] Recall: N/A (no ground truth)")

    # 记录详细指标
    if table_name:
        if table_name not in _table_metrics:
            _table_metrics[table_name] = {}
        _table_metrics[table_name][test_name] = {
            "doris_precision": doris_precision,
            "doris_recall": doris_recall,
            "faiss_precision": faiss_precision,
            "faiss_recall": faiss_recall,
            "overlap": overlap,
        }

def print_comparison_summary():
    """输出精度-召回率-重叠比例表格和图像，并增加FAISS原生结果表格"""
    logger.info("\n" + "="*80)
    logger.info("SUMMARY: Doris Precision/Recall/Overlap (ID+Distance Match)")
    logger.info("="*80)

    # Doris表格
    if _table_metrics:
        import tabulate
        headers = [
            "Table",
            "Range Doris P", "Range Doris R", "Range Overlap",
            "TopN Doris P", "TopN Doris R", "TopN Overlap",
            "Compound Doris P", "Compound Doris R", "Compound Overlap"
        ]
        rows = []
        for table in sorted(_table_metrics.keys()):
            row = [table]
            # Range Search
            m = _table_metrics[table].get("Range Search", {})
            row.append(f"{(m.get('doris_precision', 0)*100):.2f}" if m.get('doris_precision') is not None else "")
            row.append(f"{(m.get('doris_recall', 0)*100):.2f}" if m.get('doris_recall') is not None else "")
            row.append(f"{(m.get('overlap', 0)*100):.2f}" if m.get('overlap') is not None else "")
            # Top-N Search
            m = _table_metrics[table].get("Top-N Search", {})
            row.append(f"{(m.get('doris_precision', 0)*100):.2f}" if m.get('doris_precision') is not None else "")
            row.append(f"{(m.get('doris_recall', 0)*100):.2f}" if m.get('doris_recall') is not None else "")
            row.append(f"{(m.get('overlap', 0)*100):.2f}" if m.get('overlap') is not None else "")
            # Compound Search
            m = _table_metrics[table].get("Compound Search", {})
            row.append(f"{(m.get('doris_precision', 0)*100):.2f}" if m.get('doris_precision') is not None else "")
            row.append(f"{(m.get('doris_recall', 0)*100):.2f}" if m.get('doris_recall') is not None else "")
            row.append(f"{(m.get('overlap', 0)*100):.2f}" if m.get('overlap') is not None else "")
            rows.append(row)
        try:
            table_str = tabulate.tabulate(rows, headers, tablefmt="github")
        except Exception:
            table_str = "\n".join(
                ["\t".join(headers)] +
                ["\t".join(row) for row in rows]
            )
        logger.info("\nDORIS PRECISION/RECALL/OVERLAP TABLE:\n" + table_str)

    # ===== 新增：打印FAISS原生结果表格 =====
    # 只打印faiss的precision/recall（与ground truth的对比），不打印overlap
    faiss_headers = [
        "Table",
        "Range Faiss P", "Range Faiss R",
        "TopN Faiss P", "TopN Faiss R",
        "Compound Faiss P", "Compound Faiss R"
    ]
    faiss_rows = []
    for table in sorted(_table_metrics.keys()):
        row = [table]
        # Range Search
        m = _table_metrics[table].get("Range Search", {})
        row.append(f"{(m.get('faiss_precision', 0)*100):.2f}" if m.get('faiss_precision') is not None else "")
        row.append(f"{(m.get('faiss_recall', 0)*100):.2f}" if m.get('faiss_recall') is not None else "")
        # Top-N Search
        m = _table_metrics[table].get("Top-N Search", {})
        row.append(f"{(m.get('faiss_precision', 0)*100):.2f}" if m.get('faiss_precision') is not None else "")
        row.append(f"{(m.get('faiss_recall', 0)*100):.2f}" if m.get('faiss_recall') is not None else "")
        # Compound Search
        m = _table_metrics[table].get("Compound Search", {})
        row.append(f"{(m.get('faiss_precision', 0)*100):.2f}" if m.get('faiss_precision') is not None else "")
        row.append(f"{(m.get('faiss_recall', 0)*100):.2f}" if m.get('faiss_recall') is not None else "")
        faiss_rows.append(row)
    try:
        faiss_table_str = tabulate.tabulate(faiss_rows, faiss_headers, tablefmt="github")
    except Exception:
        faiss_table_str = "\n".join(
            ["\t".join(faiss_headers)] +
            ["\t".join(row) for row in faiss_rows]
        )
    logger.info("\nFAISS PRECISION/RECALL TABLE:\n" + faiss_table_str)

    # 只画 Top-N Search 的精度和召回率
    table_points = []
    for table, metrics in _table_metrics.items():
        m = metrics.get("Top-N Search", {})
        if m.get("doris_precision") is not None and m.get("doris_recall") is not None:
            table_points.append({
                "table": table,
                "precision": m["doris_precision"],
                "recall": m["doris_recall"],
            })

    if table_points:
        for p in table_points:
            parts = p["table"].split("_")
            p["dim"] = int(parts[1])
            p["num"] = int(parts[3])

        plt.figure(figsize=(10, 7))
        dims = sorted(set(p["dim"] for p in table_points))
        colors = plt.cm.get_cmap('tab20', len(dims))
        for idx, dim in enumerate(dims):
            group = [p for p in table_points if p["dim"] == dim]
            group = sorted(group, key=lambda x: x["num"])
            plt.plot(
                [g["recall"] for g in group],
                [g["precision"] for g in group],
                marker='o',
                label=f'dim={dim}',
                color=colors(idx)
            )
            for g in group:
                plt.text(g["recall"], g["precision"], g["table"], fontsize=7)
        plt.xlabel("Recall")
        plt.ylabel("Precision")
        plt.title("Doris Precision-Recall by Dimension (Top-N Search, ID+Distance Match)")
        plt.legend()
        plt.grid(True)
        img_path1 = "summary_precision_recall_by_dim.png"
        plt.savefig(img_path1)
        logger.info(f"Saved precision-recall plot by dimension to {img_path1}")
        plt.close()

        plt.figure(figsize=(10, 7))
        nums = sorted(set(p["num"] for p in table_points))
        colors = plt.cm.get_cmap('tab20', len(nums))
        for idx, num in enumerate(nums):
            group = [p for p in table_points if p["num"] == num]
            group = sorted(group, key=lambda x: x["dim"])
            plt.plot(
                [g["recall"] for g in group],
                [g["precision"] for g in group],
                marker='o',
                label=f'num={num}',
                color=colors(idx)
            )
            for g in group:
                plt.text(g["recall"], g["precision"], g["table"], fontsize=7)
        plt.xlabel("Recall")
        plt.ylabel("Precision")
        plt.title("Doris Precision-Recall by Row Count (Top-N Search, ID+Distance Match)")
        plt.legend()
        plt.grid(True)
        img_path2 = "summary_precision_recall_by_num.png"
        plt.savefig(img_path2)
        logger.info(f"Saved precision-recall plot by row count to {img_path2}")
        plt.close()
def brute_force_topn(query_vector: np.ndarray, embeddings: np.ndarray, ids: np.ndarray, topk: int) -> List[Tuple[int, float]]:
    """暴力计算topk ground truth（数组版，保留以兼容旧用法）"""
    dists = np.linalg.norm(embeddings - query_vector, axis=1)
    idxs = np.argsort(dists)[:topk]
    return [(int(ids[i]), float(dists[i])) for i in idxs]

def brute_force_topn_streaming(query_vector: np.ndarray, files: List[str], topk: int) -> List[Tuple[int, float]]:
    """在不加载全量内存的情况下，流式计算全表的topk ground truth。"""
    import heapq
    # max-heap by negative distance to keep smallest topk
    heap: List[Tuple[float, int]] = []  # (-dist, id)
    q = query_vector.astype(np.float32)
    for fp in files:
        with open(fp, "r") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                try:
                    vid = int(parts[0])
                    vec = np.fromstring(parts[2].strip('[]'), sep=",", dtype=np.float32)
                except Exception:
                    continue
                # compute l2
                dist = float(np.linalg.norm(vec - q))
                if len(heap) < topk:
                    heapq.heappush(heap, (-dist, vid))
                else:
                    if -heap[0][0] > dist:
                        heapq.heapreplace(heap, (-dist, vid))
    # extract and sort by distance asc
    results = [(vid, -negd) for (negd, vid) in heap]
    results.sort(key=lambda x: x[1])
    return results

def brute_force_range_streaming(query_vector: np.ndarray, files: List[str], radius: float) -> List[Tuple[int, float]]:
    """流式计算全表在指定半径内的所有点，返回按距离升序列表。"""
    q = query_vector.astype(np.float32)
    res: List[Tuple[int, float]] = []
    r = float(radius)
    for fp in files:
        with open(fp, "r") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                try:
                    vid = int(parts[0])
                    vec = np.fromstring(parts[2].strip('[]'), sep=",", dtype=np.float32)
                except Exception:
                    continue
                dist = float(np.linalg.norm(vec - q))
                if dist < r:
                    res.append((vid, dist))
    res.sort(key=lambda x: x[1])
    return res

def main() -> None:
    # ===== 新增：模式选择 =====
    do_range_search = True
    do_topn_search = True
    do_compound_search = True

    # 移除硬编码的表列表，改为动态获取
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'data')
    
    # Connect to Doris
    conn = get_conn()
    cursor = conn.cursor()
    
    # 动态获取数据库中的表
    try:
        cursor.execute(f"USE vector_test;")
        cursor.execute("SHOW TABLES;")
        all_tables = cursor.fetchall()
        
        # 提取表名并过滤出符合命名规范的表（dim_X_num_Y格式）
        tables = []
        for table_row in all_tables:
            table_name = table_row[0]  # 表名在第一列
            # 检查表名是否符合 dim_X_num_Y 的格式
            if table_name.startswith('dim_') and '_num_' in table_name:
                try:
                    parts = table_name.split('_')
                    if len(parts) == 4 and parts[0] == 'dim' and parts[2] == 'num':
                        # 验证维度和数量是否为数字
                        int(parts[1])  # dimension
                        int(parts[3])  # number
                        tables.append(table_name)
                except (ValueError, IndexError):
                    # 如果解析失败，跳过这个表
                    continue
        
        tables.sort()  # 排序以保持一致的处理顺序
        logger.info(f"Found {len(tables)} tables to test: {tables}")
        
        if not tables:
            logger.error("No tables found with the expected naming pattern (dim_X_num_Y)")
            return
            
    except Exception as e:
        logger.error(f"Failed to get table list: {e}")
        return
    
    for table in tables:
        logger.info(f"Processing table: {table}")
        
        # Extract dimension from table name
        try:
            dimension = int(table.split("_")[1])
        except (ValueError, IndexError):
            logger.error(f"Could not extract dimension from table name: {table}")
            continue
        
        # Build FAISS index over the entire table using streaming from TSV files
        files = get_table_tsv_files(data_dir, table)
        if not files:
            logger.warning(f"No TSV files found for table {table} in {data_dir}")
            continue
        index, sample_ids, sample_embeddings = build_faiss_index_from_tsv_files(
            files, index_type="hnsw", metric_type="l2", dimension=dimension
        )
        logger.info(f"Built Faiss index over entire table {table}. ntotal={index.ntotal}")
        
        # Select a random vector for querying
        if len(sample_embeddings) == 0:
            logger.error("No sample embeddings available for query selection")
            continue
        random_idx = random.randint(0, len(sample_embeddings) - 1)
        query_vector = sample_embeddings[random_idx]
        query_vector_str = str(query_vector.tolist()).replace(' ', '')
        
        # Use Doris
        # cursor.execute(f"USE vector_test_1_bucket;")
        cursor.execute(f"USE vector_test;")

        # 1. Range search with percentile-based radius
        if do_range_search:
            percentile_less = random.randint(30, 70)  # Random percentile between 30-70
            radius_less = get_radius(query_vector, sample_embeddings, percentile_less)
            logger.info(f"--- Range Search (distance < {radius_less:.2f}, {percentile_less}th percentile) ---")
            
            # Faiss range search
            faiss_range_results = faiss_range_search(index, query_vector, radius_less)
            # streaming ground truth across whole table
            ground_truth = brute_force_range_streaming(query_vector, files, radius_less)
            # Doris range search
            range_search_sql = f"""
                SELECT * FROM (SELECT id, l2_distance_approximate(embedding, {query_vector_str}) as distance, category FROM {table} WHERE l2_distance_approximate(embedding, {query_vector_str}) < {radius_less}) as SUB ORDER BY distance;"""
            if dimension <= 8:
                logger.info(f"SQL: {range_search_sql}")
            cursor.execute(range_search_sql)
            doris_range_results = cursor.fetchall()

            # 比较结果
            compare_and_log(
                faiss_range_results,
                doris_range_results,
                "Range Search",
                dimension,
                table_name=table,
                ground_truth=ground_truth
            )

        # 3. Top-N search
        if do_topn_search:
            logger.info("--- Top-N Search ---")
            
            # 随机生成topK
            topk = random.randint(3, 100)
            logger.info(f"Top-N search with K={topk}")

            # Faiss top-N search
            faiss_topn_results = faiss_topn_search(index, query_vector, limit=topk)
            # logger.info(f"Faiss top-N search results: {faiss_topn_results}")
            
            # Doris top-N search
            topn_search_sql = f"""SELECT id, l2_distance_approximate(embedding, {query_vector_str}), category FROM {table} ORDER BY l2_distance_approximate(embedding, {query_vector_str}) limit {topk};"""
            if dimension <= 8:
                logger.info(f"SQL: {topn_search_sql}")
            cursor.execute(topn_search_sql)
            doris_topn_results = cursor.fetchall()

            # 计算topn ground truth（暴力法）
            gt_topn = brute_force_topn_streaming(query_vector, files, topk)

            compare_and_log(
                faiss_topn_results,
                doris_topn_results,
                "Top-N Search",
                dimension,
                table_name=table,
                ground_truth=gt_topn
            )

        # 4. Compound search with percentile-based radius
        if do_compound_search:
            percentile_compound = random.randint(10, 40)  # Random percentile between 10-40
            radius_compound = get_radius(query_vector, sample_embeddings, percentile_compound)
            # 随机生成compound search的topK
            compound_topk = random.randint(3, 10)
            logger.info(f"--- Compound Search (distance < {radius_compound:.2f}, {percentile_compound}th percentile, and sorted, K={compound_topk}) ---")
            
            # Faiss implementation of compound search
            faiss_compound_results = faiss_compound_search(index, query_vector, radius_compound, compound_topk)
            faiss_compound_results.sort(key=lambda x: x[1])  # Sort by distance
            logger.info(f"Faiss compound search results: {faiss_compound_results}")
            
            # Doris compound search
            compound_search_sql = f"""SELECT id, l2_distance_approximate(embedding, {query_vector_str}) as distance, category FROM {table} WHERE l2_distance_approximate(embedding, {query_vector_str}) < {radius_compound} ORDER BY distance limit {compound_topk};"""
            if dimension <= 8:
                logger.info(f"SQL: {compound_search_sql}")
            cursor.execute(compound_search_sql)
            doris_compound_results = cursor.fetchall()
            logger.info(f"Doris compound search results: {doris_compound_results}")

            # 计算compound ground truth（暴力法+距离过滤+排序+topk）
            # approximate ground truth using sample for compound
            dists = np.linalg.norm(sample_embeddings - query_vector, axis=1)
            mask = dists < radius_compound
            filtered_ids = sample_ids[mask]
            filtered_dists = dists[mask]
            idxs = np.argsort(filtered_dists)[:compound_topk]
            gt_compound = [(int(filtered_ids[i]), float(filtered_dists[i])) for i in idxs]
            logger.info(f"Ground truth for compound search: {gt_compound}")
            compare_and_log(
                faiss_compound_results,
                doris_compound_results,
                "Compound Search",
                dimension,
                table_name=table,
                ground_truth=gt_compound
            )

        logger.info(f"Completed comparison for table {table}\n" + "-"*50)
    
    # Print summary of all test results
    print_comparison_summary()

if __name__ == "__main__":
    main()