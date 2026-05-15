import numpy as np
from sklearn.cluster import KMeans

# 参数
d = 4         # 向量维度
M = 2         # 子向量数
nbits = 2     # 每个子向量用 2 bit -> 4 个质心
K = 2 ** nbits
N = 5         # 数据量

# 构造一些 toy 数据
np.random.seed(123)
X = np.random.randn(N, d).astype(np.float32)

# 训练 PQ 码本
subdim = d // M
codebooks = []
for m in range(M):
    subvectors = X[:, m*subdim:(m+1)*subdim]
    kmeans = KMeans(n_clusters=K, random_state=0).fit(subvectors)
    codebooks.append(kmeans.cluster_centers_)

# 编码：存储每个向量的 PQ 索引
codes = np.zeros((N, M), dtype=np.int32)
for i in range(N):
    for m in range(M):
        subv = X[i, m*subdim:(m+1)*subdim]
        centroids = codebooks[m]
        dist = np.linalg.norm(subv - centroids, axis=1)
        codes[i, m] = np.argmin(dist)

print("原始数据:\n", X)
print("编码结果:\n", codes)

# 查询向量
q = np.random.randn(d).astype(np.float32)

# Step1: 构建查找表
LUT = np.zeros((M, K))
for m in range(M):
    q_subv = q[m*subdim:(m+1)*subdim]
    centroids = codebooks[m]
    LUT[m, :] = np.linalg.norm(q_subv - centroids, axis=1)**2

print("查找表 (LUT):\n", LUT)

# Step2: 用查找表计算查询到每个向量的距离
distances = []
for i in range(N):
    d_hat = 0
    for m in range(M):
        d_hat += LUT[m, codes[i, m]]
    distances.append(d_hat)

print("近似距离:", distances)
print("真实距离:", np.linalg.norm(X - q, axis=1)**2)
