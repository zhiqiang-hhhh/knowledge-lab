import numpy as np
from sklearn.cluster import KMeans

# 构造 10 个 8 维向量
vecs = np.array([
    [0.1, 0.2, 1.0,  1.1, 10.0, 10.2, 50.0, 50.1],
    [0.2, 0.3, 1.1,  1.0, 10.1, 10.3, 50.2, 50.0],
    [0.15,0.25,1.05, 1.05,10.05,10.25,50.1, 50.05],  
    [5.0, 5.1, 1.0,  1.2, 20.0, 20.1, 60.0, 60.2],   
    [5.2, 5.0, 1.1,  1.3, 20.1, 20.0, 60.1, 60.3],  
    [9.0, 9.2, 2.0,  2.1, 30.0, 30.2, 70.0, 70.1],
    [9.1, 9.3, 2.1,  2.0, 30.1, 30.3, 70.2, 70.0],
    [15.0,15.1,3.0,  3.1, 40.0, 40.1, 80.0, 80.2],
    [15.1,15.2,3.1,  3.0, 40.1, 40.2, 80.1, 80.3],
    [20.0,20.1,4.0,  4.1, 50.0, 50.1, 90.0, 90.2],
])

# 取第一个维度
dim0 = vecs[:, 0].reshape(-1, 1)

# KMeans 聚类 (5个质心)
kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
kmeans.fit(dim0)

# 质心
centroids = kmeans.cluster_centers_.flatten()
# 排序后方便对照
sorted_centroids = np.sort(centroids)

print("质心:", sorted_centroids)

# 每个点的质心 ID (用排序后的索引)
labels = []
for x in dim0.flatten():
    # 找最近质心的 index
    idx = np.argmin(np.abs(sorted_centroids - x))
    labels.append(idx)
labels = np.array(labels)

print("编码 (INT8):", labels)

# 解码 (用质心替换)
decoded = sorted_centroids[labels]
print("解码值:", decoded)

# 计算 MSE
mse = np.mean((dim0.flatten() - decoded) ** 2)
print("MSE:", mse)
