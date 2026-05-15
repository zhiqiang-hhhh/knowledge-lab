import numpy as np
import faiss
from sklearn.cluster import KMeans
import time, sys

# -----------------------
# 参数设置
# -----------------------
N, D = 20000, 128     # 数据集大小
NQ = 2000             # 查询数
K = 10                # Top-K
M, nbits = 16, 8      # PQ 参数 (d/M per subvector, 2^nbits centroids)

xb = np.random.random((N, D)).astype('float32')
xq = np.random.random((NQ, D)).astype('float32')

# -----------------------
# 工具函数
# -----------------------
def time_ms():
    return time.time() * 1000

def recall(I_true, I_test):
    n, k = I_true.shape
    return np.mean([
        len(set(I_true[i]) & set(I_test[i])) / k
        for i in range(n)
    ])

def sizeof_mb(nbytes):
    return nbytes / (1024**2)

# -----------------------
# 1. IndexFlat (baseline)
# -----------------------
t0 = time_ms()
index_flat = faiss.IndexFlatL2(D)
index_flat.add(xb)
t1 = time_ms()
D_ref, I_ref = index_flat.search(xq, K)
t2 = time_ms()

flat_train_time = 0
flat_build_time = t1 - t0
flat_search_time = (t2 - t1) * 1000 / NQ  # μs/query
flat_mem = N * D * 4  # float32
print("IndexFlat done.")

# -----------------------
# 2. Scalar Quantization
# -----------------------
def scalar_quantize(x, k=256):
    N, D = x.shape
    centroids = []
    codes = np.zeros((N, D), dtype=np.uint8)
    for d in range(D):
        km = KMeans(n_clusters=min(k, N), n_init=5).fit(x[:, d:d+1])
        centroids.append(km.cluster_centers_.astype('float32'))
        codes[:, d] = km.predict(x[:, d:d+1]).astype('uint8')
    return centroids, codes

t0 = time_ms()
centroids_per_dim, codes_scalar = scalar_quantize(xb, k=256)
t1 = time_ms()
# 解码
xb_scalar = np.zeros_like(xb)
for d in range(D):
    xb_scalar[:, d] = centroids_per_dim[d][codes_scalar[:, d], 0]
# 构建索引
index_scalar = faiss.IndexFlatL2(D)
index_scalar.add(xb_scalar)
t2 = time_ms()
# 搜索
D_scalar, I_scalar = index_scalar.search(xq, K)
t3 = time_ms()

scalar_train_time = t1 - t0
scalar_build_time = t2 - t1
scalar_search_time = (t3 - t2) * 1000 / NQ
scalar_mem = N * D * 1 + D * 256 * 4   # codes + centroids
print("Scalar quantization done.")

# -----------------------
# 3. Product Quantization (PQ)
# -----------------------
t0 = time_ms()
index_pq = faiss.IndexPQ(D, M, nbits)
index_pq.train(xb)
t1 = time_ms()
index_pq.add(xb)
t2 = time_ms()
D_pq, I_pq = index_pq.search(xq, K)
t3 = time_ms()

pq_train_time = t1 - t0
pq_build_time = t2 - t1
pq_search_time = (t3 - t2) * 1000 / NQ
pq_mem = N * M * (nbits // 8) + M * (2**nbits) * (D // M) * 4
print("PQ done.")

# -----------------------
# 4. 结果对比表
# -----------------------
results = [
    ["IndexFlat", flat_train_time, flat_build_time, flat_train_time+flat_build_time,
     flat_search_time, 100.0, sizeof_mb(flat_mem), "—", "—"],

    ["Scalar", scalar_train_time, scalar_build_time, scalar_train_time+scalar_build_time,
     scalar_search_time, recall(I_ref, I_scalar)*100,
     sizeof_mb(scalar_mem), f"{flat_mem/scalar_mem:.2f}x", f"{flat_search_time/scalar_search_time:.2f}x"],

    ["PQ", pq_train_time, pq_build_time, pq_train_time+pq_build_time,
     pq_search_time, recall(I_ref, I_pq)*100,
     sizeof_mb(pq_mem), f"{flat_mem/pq_mem:.2f}x", f"{flat_search_time/pq_search_time:.2f}x"],
]

header = ["方法","训练时间 (ms)","构建时间 (ms)","总时间 (ms)","搜索时间 (μs/query)","召回率 (%)",
          "内存使用 (MB)","内存节省","相对 IndexFlat 性能对比"]

row_format = "{:<10} {:>15} {:>15} {:>15} {:>20} {:>12} {:>15} {:>12} {:>15}"
print("\n" + row_format.format(*header))
for row in results:
    print(row_format.format(*row))
