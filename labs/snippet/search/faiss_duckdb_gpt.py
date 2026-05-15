import numpy as np
import pandas as pd
import faiss
import duckdb

# -----------------------------
# 向量数据
# -----------------------------
xb = np.array([
    [1.0, 0.0, 0.9],
    [1.0, 0.0, 0.8],
    [1.0, 0.0, 0.7],
], dtype='float32')

xq = np.array([[3.0, 1.0, 2.0]], dtype='float32')

def normalize(v):
    return v / np.linalg.norm(v, axis=1, keepdims=True)

# -----------------------------
# Faiss 部分
# -----------------------------
print("== Faiss ==")

# L2
index_l2 = faiss.IndexFlatL2(3)
index_l2.add(xb)
D_l2, I_l2 = index_l2.search(xq, k=2)
print("\n[Faiss] L2 Distance")
for i, d in zip(I_l2[0], D_l2[0]):
    print(f"Index: {i}, Distance: {d:.4f}, Vector: {xb[i]}")

# Inner Product
index_ip = faiss.IndexFlatIP(3)
index_ip.add(xb)
D_ip, I_ip = index_ip.search(xq, k=2)
print("\n[Faiss] Inner Product (larger = more similar)")
for i, d in zip(I_ip[0], D_ip[0]):
    print(f"Index: {i}, IP Score: {d:.4f}, Vector: {xb[i]}")

# Cosine (normalize first)
xb_norm = normalize(xb)
xq_norm = normalize(xq)
index_cos = faiss.IndexFlatIP(3)
index_cos.add(xb_norm)
D_cos, I_cos = index_cos.search(xq_norm, k=2)
print("\n[Faiss] Cosine Similarity (via normalized inner product)")
for i, d in zip(I_cos[0], D_cos[0]):
    print(f"Index: {i}, CosSim: {d:.4f}, Vector: {xb[i]}")

# -----------------------------
# DuckDB 部分
# -----------------------------
print("\n== DuckDB ==")

con = duckdb.connect()
con.execute("INSTALL vss; LOAD vss")
con.execute("CREATE TABLE vecs(id INTEGER, v FLOAT[3])")
con.execute("CREATE INDEX my_hnsw_index ON vecs USING HNSW (v);")
df = pd.DataFrame({'id': range(len(xb)), 'v': list(xb)})
con.execute("INSERT INTO vecs SELECT * FROM df")

# L2
res_l2 = con.execute("""
    SELECT id, v, array_distance(v, [3.0, 1.0, 2.0]::FLOAT[3]) AS dist
    FROM vecs
    ORDER BY dist ASC
    LIMIT 2
""").fetchall()
print("\n[DuckDB] L2 Distance")
for row in res_l2:
    print(f"Index: {row[0]}, Distance: {row[2]:.4f}, Vector: {row[1]}")

# Inner Product
res_ip = con.execute("""
    SELECT id, v, array_negative_inner_product(v, [3.0, 1.0, 2.0]::FLOAT[3]) AS score
    FROM vecs
    ORDER BY score DESC
    LIMIT 2
""").fetchall()
print("\n[DuckDB] Inner Product (larger = more similar)")
for row in res_ip:
    print(f"Index: {row[0]}, IP Score: {row[2]:.4f}, Vector: {row[1]}")
    
expr1 = con.execute("""
    explain 
    SELECT id, v, array_inner_product(v, [3.0, 1.0, 2.0]::FLOAT[3]) AS score
    FROM vecs
    ORDER BY score DESC
    LIMIT 2
""").fetchall()
print("\n[DuckDB] Explain Inner Product")
for row in expr1:
    print(f"{row}\n")
    
expr2 = con.execute("""
    explain 
    SELECT id, v, array_negative_inner_product(v, [3.0, 1.0, 2.0]::FLOAT[3]) AS score
    FROM vecs
    ORDER BY score DESC
    LIMIT 2
""").fetchall()

print("\n[DuckDB] Explain Negative Inner Product")
for row in expr2:
    print(f"{row}\n")

# Cosine
res_cos = con.execute("""
    SELECT id, v, array_cosine_distance(v, [3.0, 1.0, 2.0]::FLOAT[3]) AS dist
    FROM vecs
    ORDER BY dist ASC
    LIMIT 2
""").fetchall()
print("\n[DuckDB] Cosine Distance (smaller = more similar)")
for row in res_cos:
    print(f"Index: {row[0]}, Cosine Distance: {row[2]:.4f}, Vector: {row[1]}")


