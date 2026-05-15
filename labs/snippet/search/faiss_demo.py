import faiss
import numpy as np

# 创建一些简单的向量
xb = np.array([
    [1.0, 0.0],
    [0.0, 1.0],
    [1.0, 1.0],
    [-1.0, -1.0],
], dtype='float32')

xq = np.array([[1.0, 1.0]], dtype='float32')  # 查询向量

def print_results(D, I, method):
    print(f"\n=== {method} ===")
    for i, (dist, idx) in enumerate(zip(D[0], I[0])):
        print(f"{i+1}. Index={idx}, Distance/Score={dist:.4f}, Vector={xb[idx]}")

# ------------------------------
# L2 距离索引（欧几里得距离，越小越相似）
# ------------------------------
index_l2 = faiss.IndexFlatL2(2)
index_l2.add(xb)

D_l2, I_l2 = index_l2.search(xq, k=3)
print_results(D_l2, I_l2, "L2 距离 (越小越近)")

# ------------------------------
# Inner Product 索引（内积，越大越相似）
# ------------------------------
index_ip = faiss.IndexFlatIP(2)
index_ip.add(xb)

D_ip, I_ip = index_ip.search(xq, k=3)
print_results(D_ip, I_ip, "内积 (越大越相似)")

# ------------------------------
# 归一化后使用 Inner Product 模拟余弦相似度
# ------------------------------
def normalize(v):
    return v / np.linalg.norm(v, axis=1, keepdims=True)

xb_norm = normalize(xb)
xq_norm = normalize(xq)

index_cosine = faiss.IndexFlatIP(2)
index_cosine.add(xb_norm)

D_cos, I_cos = index_cosine.search(xq_norm, k=3)
print_results(D_cos, I_cos, "余弦相似度 (通过归一化 + 内积)")
