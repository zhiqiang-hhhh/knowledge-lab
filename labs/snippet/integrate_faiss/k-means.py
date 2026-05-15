import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import mean_squared_error

# 随机生成一些 16D 向量
np.random.seed(42)
data = np.random.randn(1000, 16) * [1,5,10,0.5,3,8,2,1,4,6,2,5,1,7,3,2]  # 每个维度不同scale

# -----------------------------
# 方式 A：整条 16D 向量聚类
# -----------------------------
kmeans_A = KMeans(n_clusters=256, random_state=42, n_init="auto")
kmeans_A.fit(data)
codes_A = kmeans_A.predict(data)
decoded_A = kmeans_A.cluster_centers_[codes_A]

mse_A = mean_squared_error(data, decoded_A)
print(f"方式 A (16D 聚类) MSE: {mse_A:.4f}")

# -----------------------------
# 方式 B：切成 16 个 1D sub-vector 聚类
# -----------------------------
decoded_B = np.zeros_like(data)
for d in range(data.shape[1]):
    dim_data = data[:, d].reshape(-1, 1)
    kmeans_B = KMeans(n_clusters=16, random_state=42, n_init="auto")  # 每维单独少点质心
    kmeans_B.fit(dim_data)
    codes_B = kmeans_B.predict(dim_data)
    decoded_B[:, d] = kmeans_B.cluster_centers_[codes_B].flatten()

mse_B = mean_squared_error(data, decoded_B)
print(f"方式 B (16 个 1D 聚类) MSE: {mse_B:.4f}")
