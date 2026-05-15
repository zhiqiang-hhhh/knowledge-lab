import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import mean_squared_error
import matplotlib.pyplot as plt

# 随机生成一些 16D 向量
np.random.seed(42)
data = np.random.randn(2000, 16) * np.linspace(1, 8, 16)  # scale 不同维度

def pq_encode_decode(data, m, total_centroids=256):
    """
    对 data 做 PQ 编码/解码，返回 MSE
    :param data: 原始数据 (N, D)
    :param m: sub-vector 个数
    :param total_centroids: 总质心数
    """
    n, d = data.shape
    assert d % m == 0, "维度必须能被 m 整除"
    sub_dim = d // m
    k = total_centroids // m  # 每个 sub-vector 的质心数

    decoded = np.zeros_like(data, dtype=np.float32)

    for i in range(m):
        sub_data = data[:, i*sub_dim:(i+1)*sub_dim]
        kmeans = KMeans(n_clusters=k, random_state=42, n_init="auto")
        kmeans.fit(sub_data)
        codes = kmeans.predict(sub_data)
        decoded[:, i*sub_dim:(i+1)*sub_dim] = kmeans.cluster_centers_[codes]

    return mean_squared_error(data, decoded)

# 实验：m = 1, 2, 4, 8, 16
mses = []
ms = [1, 2, 4, 8, 16]
for m in ms:
    mse = pq_encode_decode(data, m, total_centroids=256)
    mses.append(mse)
    print(f"m={m}, sub-dim={16//m}, MSE={mse:.4f}")

# 画图
plt.plot(ms, mses, marker="o")
plt.xlabel("Number of sub-vectors (m)")
plt.ylabel("Reconstruction MSE")
plt.title("PQ: MSE vs number of sub-vectors (fixed total centroids=256)")
plt.grid(True)
plt.show()
