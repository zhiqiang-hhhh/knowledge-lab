"""
Doris ANN Top-N Search Demo
============================
演示如何在 Apache Doris 中使用 HNSW 向量索引进行 ANN Top-N 近邻搜索。

流程: 建表 → 导入向量数据 → 创建 ANN 索引 → Top-N 搜索 → 与暴力搜索对比 Recall

用法:
    python ann_topn_demo.py
    python ann_topn_demo.py --host 127.0.0.1 --port 9030 --dim 32 --num 2000 --topn 10
"""

import argparse
import time
import numpy as np
import mysql.connector


# ============ 连接 & 工具函数 ============

def get_conn(host, port, user, password, db):
    return mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=db
    )


def fmt_vec(vec):
    """将 numpy 向量格式化为 Doris ARRAY 字面量: [0.1,0.2,...]"""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def execute(conn, sql, fetch=False):
    cur = conn.cursor()
    cur.execute(sql)
    if fetch:
        rows = cur.fetchall()
        cur.close()
        return rows
    cur.close()


# ============ DDL ============

TABLE = "ann_topn_demo"


def setup_table(conn, dim):
    """建表 + 插入数据前的准备。"""
    execute(conn, f"DROP TABLE IF EXISTS {TABLE}")
    execute(conn, f"""
        CREATE TABLE {TABLE} (
            id INT NOT NULL,
            embedding ARRAY<FLOAT> NOT NULL
        ) ENGINE=OLAP
        DUPLICATE KEY(id)
        DISTRIBUTED BY HASH(id) BUCKETS 1
        PROPERTIES ("replication_num" = "1")
    """)
    print(f"  表 {TABLE} 已创建")


def insert_vectors(conn, vectors, batch_size=500):
    """批量插入向量。"""
    n = len(vectors)
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        values = []
        for i in range(start, end):
            values.append(f"({i}, {fmt_vec(vectors[i])})")
        sql = f"INSERT INTO {TABLE} VALUES {','.join(values)}"
        execute(conn, sql)
        if (end) % (max(n // 5, 1)) == 0 or end == n:
            print(f"  已插入 {end}/{n}")


def create_ann_index(conn, dim):
    """创建 HNSW ANN 索引并等待构建完成。"""
    execute(conn, f"""
        CREATE INDEX idx_ann ON {TABLE}(`embedding`) USING ANN PROPERTIES(
            "index_type" = "hnsw",
            "metric_type" = "l2_distance",
            "dim" = "{dim}"
        )
    """)
    print("  ANN 索引已创建，开始 BUILD...")
    execute(conn, f"BUILD INDEX idx_ann ON {TABLE}")
    time.sleep(2)
    print("  ANN 索引 BUILD 完成")


# ============ 搜索 ============

def ann_search_topn(conn, query, topn):
    """ANN 近似 Top-N 搜索 (走 HNSW 索引)。"""
    sql = f"""
        SELECT id, l2_distance_approximate(embedding, {fmt_vec(query)}) AS dist
        FROM {TABLE}
        ORDER BY l2_distance_approximate(embedding, {fmt_vec(query)}) ASC
        LIMIT {topn}
    """
    return execute(conn, sql, fetch=True)


def brute_force_topn(conn, query, topn):
    """暴力精确 Top-N 搜索 (不走索引)。"""
    sql = f"""
        SELECT id, l2_distance(embedding, {fmt_vec(query)}) AS dist
        FROM {TABLE}
        ORDER BY l2_distance(embedding, {fmt_vec(query)}) ASC
        LIMIT {topn}
    """
    return execute(conn, sql, fetch=True)


def ann_search_topn_prepared(conn, query, topn):
    """ANN Top-N 搜索 — 使用 Prepared Statement，向量通过参数绑定传入。"""
    sql = f"""
        SELECT id, l2_distance_approximate(embedding, CAST(%s AS ARRAY<FLOAT>)) AS dist
        FROM {TABLE}
        ORDER BY l2_distance_approximate(embedding, CAST(%s AS ARRAY<FLOAT>)) ASC
        LIMIT {topn}
    """
    vec_str = fmt_vec(query)
    cur = conn.cursor(prepared=True)
    cur.execute(sql, (vec_str, vec_str))
    rows = cur.fetchall()
    cur.close()
    return rows


# ============ 主流程 ============

def main():
    parser = argparse.ArgumentParser(description="Doris ANN Top-N Search Demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9930)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--db", default="test_demo")
    parser.add_argument("--dim", type=int, default=32)
    parser.add_argument("--num", type=int, default=2000, help="向量数量")
    parser.add_argument("--topn", type=int, default=5)
    parser.add_argument("--queries", type=int, default=5, help="查询次数")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    np.random.seed(args.seed)

    print(f"=== Doris ANN Top-{args.topn} Search Demo ===")
    print(f"连接: {args.host}:{args.port}, 库: {args.db}")
    print(f"数据: {args.num} vectors, dim={args.dim}\n")

    conn = get_conn(args.host, args.port, args.user, args.password, args.db)
    execute(conn, "SET enable_common_expr_pushdown = true")

    # 1. 建表 & 插入数据
    print("[1/4] 建表...")
    setup_table(conn, args.dim)

    print("[2/4] 插入向量数据...")
    vectors = np.random.randn(args.num, args.dim).astype(np.float32)
    insert_vectors(conn, vectors)

    # 2. 创建 ANN 索引
    print("[3/4] 创建 ANN 索引...")
    create_ann_index(conn, args.dim)

    # 3. Top-N 搜索
    print(f"[4/4] 执行 {args.queries} 次 Top-{args.topn} 搜索...\n")
    queries = np.random.randn(args.queries, args.dim).astype(np.float32)

    recalls = []
    for qi in range(args.queries):
        q = queries[qi]

        t0 = time.perf_counter()
        ann_res = ann_search_topn(conn, q, args.topn)
        ann_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        gt_res = brute_force_topn(conn, q, args.topn)
        bf_ms = (time.perf_counter() - t0) * 1000

        ann_ids = {row[0] for row in ann_res}
        gt_ids = {row[0] for row in gt_res}
        recall = len(ann_ids & gt_ids) / len(gt_ids)
        recalls.append(recall)

        if qi == 0:
            print(f"--- Query 0 详细对比 (Top-{args.topn}) ---")
            print(f"{'排名':<6}{'ANN ID':<10}{'ANN Dist':<14}{'GT ID':<10}{'GT Dist':<14}{'匹配'}")
            print("-" * 60)
            for i in range(args.topn):
                ai, ad = ann_res[i] if i < len(ann_res) else (-1, -1)
                gi, gd = gt_res[i]
                match = "✓" if ai == gi else ""
                print(f"{i+1:<6}{ai:<10}{ad:<14.4f}{gi:<10}{gd:<14.4f}{match}")
            print()

        print(f"  Q{qi}: ANN={ann_ms:.1f}ms, BF={bf_ms:.1f}ms, Recall@{args.topn}={recall:.0%}")

    print(f"\n=== 平均 Recall@{args.topn} = {np.mean(recalls):.2%} ===")

    # 4. Prepared Statement 方式搜索
    print(f"\n{'='*50}")
    print(f"=== Prepared Statement 方式 Top-{args.topn} 搜索 ===")
    print(f"{'='*50}\n")

    ps_recalls = []
    for qi in range(args.queries):
        q = queries[qi]

        t0 = time.perf_counter()
        ps_res = ann_search_topn_prepared(conn, q, args.topn)
        ps_ms = (time.perf_counter() - t0) * 1000

        gt_res = brute_force_topn(conn, q, args.topn)

        ps_ids = {row[0] for row in ps_res}
        gt_ids = {row[0] for row in gt_res}
        recall = len(ps_ids & gt_ids) / len(gt_ids)
        ps_recalls.append(recall)

        if qi == 0:
            print(f"--- Query 0 Prepared Statement 详细结果 (Top-{args.topn}) ---")
            print(f"{'排名':<6}{'PS ID':<10}{'PS Dist':<14}{'GT ID':<10}{'GT Dist':<14}{'匹配'}")
            print("-" * 60)
            for i in range(args.topn):
                pi, pd = ps_res[i] if i < len(ps_res) else (-1, -1)
                gi, gd = gt_res[i]
                match = "✓" if pi == gi else ""
                print(f"{i+1:<6}{pi:<10}{pd:<14.4f}{gi:<10}{gd:<14.4f}{match}")
            print()

        print(f"  Q{qi}: PreparedStmt={ps_ms:.1f}ms, Recall@{args.topn}={recall:.0%}")

    print(f"\n=== Prepared Statement 平均 Recall@{args.topn} = {np.mean(ps_recalls):.2%} ===")

    # 清理
    execute(conn, f"DROP TABLE IF EXISTS {TABLE}")
    conn.close()
    print("清理完成")


if __name__ == "__main__":
    main()
