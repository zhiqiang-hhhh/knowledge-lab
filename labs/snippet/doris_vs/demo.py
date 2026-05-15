import argparse
import csv
import itertools
import logging
import math
import os
import statistics
import time
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from doris_vector_search import AuthOptions, DorisVectorClient

HOST = "localhost"
QUERY_PORT = 6937
USER = "root"
PASSWORD = ""
DATABASE = "demo"
BASE_TABLE_NAME = os.environ.get("HNSW_BASE_TABLE", "sift_1M")
TARGET_TABLE_NAME = os.environ.get("HNSW_TARGET_TABLE", f"{BASE_TABLE_NAME}_multi")
ID_COLUMN = os.environ.get("HNSW_ID_COLUMN", "id")
BASE_ID_COLUMN = os.environ.get("HNSW_BASE_ID_COLUMN", "id")
BASE_VECTOR_COLUMN = os.environ.get("HNSW_BASE_VECTOR_COLUMN", "embedding")
DEFAULT_BUCKETS = int(os.environ.get("HNSW_TABLE_BUCKETS", "1"))

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get(
    "HNSW_DATA_DIR",
    "/mnt/disk4/hezhiqiang/code/snippet/search/data/sift1M",
)
OUTPUT_CSV = os.path.join(THIS_DIR, "hnsw_recall_results.csv")

DEFAULT_MAX_DEGREE = [32, 48, 64]
DEFAULT_EF_CONSTRUCTION = [80, 120, 160]
DEFAULT_EF_SEARCH = [32, 64, 96]
DEFAULT_NUM_QUERIES = 200
DEFAULT_TOP_K = 100
K_VALUES = [1, 10, 50, 100]

FIELDNAMES = [
    "max_degree",
    "ef_construction",
    "ef_search",
    "vector_column",
    "num_queries",
    "max_k",
    "index_build_time_s",
    "avg_latency_ms",
    "median_latency_ms",
    *[f"recall_at_{k}" for k in K_VALUES],
    "status",
    "error",
]


def parse_int_list_env(name: str, default: Sequence[int]) -> List[int]:
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    values: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            logging.warning("ignoring invalid integer '%s' for %s", part, name)
    return values or list(default)


def read_fvecs(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.int32)
    if data.size == 0:
        return np.empty((0, 0), dtype=np.float32)
    dim = data[0]
    vectors = data.reshape(-1, dim + 1)[:, 1:].view(np.float32)
    return vectors.reshape(-1, dim)


def read_ivecs(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.int32)
    if data.size == 0:
        return np.empty((0, 0), dtype=np.int32)
    dim = data[0]
    vectors = data.reshape(-1, dim + 1)[:, 1:]
    return vectors.reshape(-1, dim)


def load_sift_queries(data_dir: str) -> Tuple[np.ndarray, np.ndarray]:
    query_path = os.path.join(data_dir, "sift_query.fvecs")
    gt_path = os.path.join(data_dir, "sift_groundtruth.ivecs")
    if not os.path.isfile(query_path):
        raise FileNotFoundError(f"missing {query_path}")
    if not os.path.isfile(gt_path):
        raise FileNotFoundError(f"missing {gt_path}")
    queries = read_fvecs(query_path).astype(np.float32)
    groundtruth = read_ivecs(gt_path).astype(np.int32)
    return queries, groundtruth


def format_vector_for_log(values: Sequence[object]) -> List[object]:
    formatted: List[object] = []
    for val in values:
        if val is None:
            formatted.append(None)
            continue
        try:
            float_val = float(val)
        except (TypeError, ValueError):
            formatted.append(val)
            continue
        if math.isnan(float_val):
            formatted.append("NaN")
        else:
            formatted.append(round(float_val, 6))
    return formatted


def compute_recall(result_ids: Sequence[int], gt_ids: Sequence[int], k: int) -> float:
    target = gt_ids[:k]
    if len(target) == 0:
        return 0.0
    result_set = set(result_ids[:k])
    hits = sum(1 for item in target if item in result_set)
    return hits / len(target)


def evaluate_recall(
    table,
    vector_column: str,
    id_column: str,
    queries: Iterable[Sequence[float]],
    groundtruth: np.ndarray,
    top_k: int,
    recall_ks: Sequence[int],
) -> Tuple[Dict[int, float], List[float]]:
    recall_totals: Dict[int, float] = {k: 0.0 for k in recall_ks}
    latencies_ms: List[float] = []
    total_queries = groundtruth.shape[0]

    for idx, query in enumerate(queries):
        raw_values: List[object] = []
        query_list: List[float] = []
        has_invalid = False

        for value in query:
            raw = value.item() if isinstance(value, np.generic) else value
            raw_values.append(raw)
            if raw is None:
                has_invalid = True
                query_list.append(raw)
                continue
            try:
                float_val = float(raw)
            except (TypeError, ValueError):
                has_invalid = True
                query_list.append(raw)
                continue
            if math.isnan(float_val):
                has_invalid = True
            query_list.append(float_val)

        if not query_list:
            has_invalid = True

        start = time.perf_counter()
        try:
            rows = (
                table.search(query_list, vector_column=vector_column, metric_type="l2_distance")
                .limit(top_k)
                .select([id_column])
                .to_list()
            )
        except Exception:
            logging.error(
                "query %d failed (has_invalid=%s) vector=%s",
                idx,
                has_invalid,
                format_vector_for_log(raw_values),
                exc_info=True,
            )
            raise

        if has_invalid:
            logging.debug("query %d included invalid values", idx)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        latencies_ms.append(elapsed_ms)
        result_ids = [int(row[id_column]) for row in rows]
        gt_row = groundtruth[idx]
        for k in recall_ks:
            recall_totals[k] += compute_recall(result_ids, gt_row, k)

    recalls = {k: (recall_totals[k] / total_queries if total_queries else 0.0) for k in recall_ks}
    return recalls, latencies_ms


def write_result_row(path: str, row: Dict[str, object]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    needs_header = not os.path.isfile(path)
    with open(path, "a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if needs_header:
            writer.writeheader()
        formatted = {}
        for key in FIELDNAMES:
            value = row.get(key)
            if value is None:
                formatted[key] = ""
            elif isinstance(value, float):
                formatted[key] = f"{value:.6f}"
            else:
                formatted[key] = value
        writer.writerow(formatted)


def generate_column_name(max_degree: int, ef_construction: int) -> str:
    return f"embedding_md{max_degree}_efc{ef_construction}"


def create_multi_index_table(
    client: DorisVectorClient,
    combinations: Sequence[Tuple[int, int, int]],
    vector_dim: int,
    base_table: str,
    target_table: str,
    buckets: int,
    skip_load: bool,
) -> Tuple[Dict[Tuple[int, int], str], Dict[str, float]]:
    unique_pairs = sorted({(max_degree, ef_construction) for max_degree, ef_construction, _ in combinations})
    if not unique_pairs:
        raise ValueError("no index parameter combinations provided")

    column_map: Dict[Tuple[int, int], str] = {}
    column_defs: List[str] = [f"`{ID_COLUMN}` BIGINT NOT NULL"]
    index_defs: List[str] = []
    for max_degree, ef_construction in unique_pairs:
        column_name = generate_column_name(max_degree, ef_construction)
        column_map[(max_degree, ef_construction)] = column_name
        column_defs.append(f"`{column_name}` ARRAY<FLOAT> NOT NULL")
        index_defs.append(
            f"INDEX idx_{column_name}(`{column_name}`) USING ANN PROPERTIES(\"index_type\"=\"hnsw\",\"metric_type\"=\"l2_distance\",\"dim\"=\"{vector_dim}\",\"max_degree\"=\"{max_degree}\",\"ef_construction\"=\"{ef_construction}\")"
        )

    ddl_body = ",\n".join(f"    {line}" for line in column_defs + index_defs)
    ddl = (
        f"CREATE TABLE `{target_table}` (\n"
        f"{ddl_body}\n"
        ") ENGINE=OLAP\n"
        f"DUPLICATE KEY(`{ID_COLUMN}`)\n"
        f"DISTRIBUTED BY HASH(`{ID_COLUMN}`) BUCKETS {buckets}\n"
        "PROPERTIES (\n"
        '  "replication_num" = "1"\n'
        ");"
    )
    logging.info("creating target table %s with DDL:\n%s", target_table, ddl)
    cursor = client.connection.cursor()
    build_times: Dict[str, float] = {}
    try:
        if skip_load:
            logging.info("skip-load enabled, reusing existing table %s", target_table)
            cursor.execute(f"SHOW TABLES LIKE '{target_table}'")
            if cursor.fetchone() is None:
                raise RuntimeError(
                    f"skip-load requested but table `{target_table}` does not exist"
                )

            cursor.execute(f"DESCRIBE `{target_table}`")
            existing_columns = {str(row[0]) for row in cursor.fetchall()}
            missing_columns = [col for col in column_map.values() if col not in existing_columns]
            if missing_columns:
                raise RuntimeError(
                    "skip-load requested but table is missing columns: " + ", ".join(missing_columns)
                )
            logging.info("skip-load: skipping data reload and index rebuild")
            return column_map, build_times

        logging.info("dropping existing table %s if present", target_table)
        cursor.execute(f"DROP TABLE IF EXISTS `{target_table}`")
        client.connection.commit()

        logging.info("creating table %s with %d embedding columns", target_table, len(column_map))
        logging.info("executing DDL:\n%s", ddl)
        cursor.execute(ddl)
        client.connection.commit()

        target_columns = [ID_COLUMN] + list(column_map.values())
        select_exprs = [
            f"CAST(`{BASE_ID_COLUMN}` AS BIGINT)",
            *[f"`{BASE_VECTOR_COLUMN}`" for _ in column_map],
        ]
        insert_sql = (
            f"INSERT INTO `{target_table}` ({', '.join(f'`{col}`' for col in target_columns)})\n"
            f"SELECT {', '.join(select_exprs)} FROM `{base_table}`"
        )
        logging.info("copying data from %s into %s", base_table, target_table)
        cursor.execute(insert_sql)
        client.connection.commit()

        for (max_degree, ef_construction), column_name in column_map.items():
            idx_name = f"idx_{column_name}"
            build_sql = f"BUILD INDEX {idx_name} ON `{target_table}`"
            logging.info("building index %s", idx_name)
            build_start = time.perf_counter()
            cursor.execute(build_sql)
            client.connection.commit()
            build_times[column_name] = time.perf_counter() - build_start
            logging.info("index %s built in %.2f seconds", idx_name, build_times[column_name])

    finally:
        cursor.close()

    return column_map, build_times


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HNSW recall evaluation sweep")
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="reuse existing target table without reloading data",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s",
    )

    args = parse_args()

    max_degree_vals = parse_int_list_env("HNSW_MAX_DEGREES", DEFAULT_MAX_DEGREE)
    ef_construction_vals = parse_int_list_env("HNSW_EF_CONSTRUCTIONS", DEFAULT_EF_CONSTRUCTION)
    ef_search_vals = parse_int_list_env("HNSW_EF_SEARCHES", DEFAULT_EF_SEARCH)
    num_queries = int(os.environ.get("HNSW_NUM_QUERIES", DEFAULT_NUM_QUERIES))
    top_k = int(os.environ.get("HNSW_TOPK", DEFAULT_TOP_K))

    logging.info("loading SIFT data from %s", DATA_DIR)
    queries, groundtruth = load_sift_queries(DATA_DIR)

    num_queries = min(num_queries, queries.shape[0], groundtruth.shape[0])
    if num_queries == 0:
        raise RuntimeError("no queries available for evaluation")
    queries = queries[:num_queries]
    groundtruth = groundtruth[:num_queries]

    max_k = min(top_k, groundtruth.shape[1])
    if max_k <= 0:
        raise RuntimeError("ground truth does not provide any neighbors")
    recall_ks = [k for k in K_VALUES if k <= max_k]
    if not recall_ks:
        recall_ks = [max_k]
    logging.info("evaluating recall at k values: %s", recall_ks)

    combinations = list(itertools.product(max_degree_vals, ef_construction_vals, ef_search_vals))
    logging.info("starting sweep across %d combinations", len(combinations))

    client = DorisVectorClient(
        database=DATABASE,
        auth_options=AuthOptions(
            host=HOST,
            query_port=QUERY_PORT,
            user=USER,
            password=PASSWORD,
        ),
    )

    column_map, index_build_times = create_multi_index_table(
        client,
        combinations,
        queries.shape[1],
        BASE_TABLE_NAME,
        TARGET_TABLE_NAME,
        DEFAULT_BUCKETS,
        args.skip_load,
    )

    table = client.open_table(TARGET_TABLE_NAME)
    table.index_options.dim = queries.shape[1]

    results_summary: List[Dict[str, object]] = []

    try:
        for idx, (max_degree, ef_construction, ef_search) in enumerate(combinations, start=1):
            logging.info(
                "[%d/%d] max_degree=%d ef_construction=%d ef_search=%d",
                idx,
                len(combinations),
                max_degree,
                ef_construction,
                ef_search,
            )
            status = "ok"
            error_msg = ""
            recalls: Dict[int, float] = {k: 0.0 for k in recall_ks}
            latencies: List[float] = []

            cache_key = (max_degree, ef_construction)
            vector_column = column_map.get(cache_key)
            if not vector_column:
                status = "error"
                error_msg = f"missing vector column for parameters {cache_key}"
                logging.error(error_msg)
                row = {
                    "max_degree": max_degree,
                    "ef_construction": ef_construction,
                    "ef_search": ef_search,
                    "vector_column": "",
                    "num_queries": num_queries,
                    "max_k": max_k,
                    "index_build_time_s": float("nan"),
                    "avg_latency_ms": 0.0,
                    "median_latency_ms": 0.0,
                    "status": status,
                    "error": error_msg,
                }
                write_result_row(OUTPUT_CSV, row)
                results_summary.append(row)
                continue

            build_time = index_build_times.get(vector_column, float("nan"))

            try:
                client.with_session("hnsw_ef_search", ef_search)
                recalls, latencies = evaluate_recall(
                    table,
                    vector_column,
                    ID_COLUMN,
                    queries,
                    groundtruth,
                    max_k,
                    recall_ks,
                )
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error_msg = str(exc)
                logging.exception("combination failed")

            avg_latency = statistics.mean(latencies) if latencies else 0.0
            median_latency = statistics.median(latencies) if latencies else 0.0

            row = {
                "max_degree": max_degree,
                "ef_construction": ef_construction,
                "ef_search": ef_search,
                "vector_column": vector_column,
                "num_queries": num_queries,
                "max_k": max_k,
                "index_build_time_s": build_time,
                "avg_latency_ms": avg_latency,
                "median_latency_ms": median_latency,
                "status": status,
                "error": error_msg,
            }
            for k, value in recalls.items():
                row[f"recall_at_{k}"] = value
            for missing_key in FIELDNAMES:
                row.setdefault(missing_key, None)

            write_result_row(OUTPUT_CSV, row)
            results_summary.append(row)

    finally:
        table.close()
        client.close()

    logging.info("completed sweep. results written to %s", OUTPUT_CSV)
    for row in results_summary:
        if row.get("status") != "ok":
            continue
        logging.info(
            "max_degree=%d ef_construction=%d ef_search=%d recall@%s=%s avg_latency_ms=%.3f",
            row["max_degree"],
            row["ef_construction"],
            row["ef_search"],
            ",".join(str(k) for k in recall_ks),
            ",".join(f"{row.get(f'recall_at_{k}', float('nan')):.4f}" for k in recall_ks),
            row["avg_latency_ms"],
        )


if __name__ == "__main__":
    main()


