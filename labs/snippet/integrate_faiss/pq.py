import numpy as np
from sklearn.cluster import KMeans

# 原始数据（统一成二维向量）
data = np.array([
    [0.1, 0.0],
    [0.2, 100.1],
    [0.3, 100.1],
    [0.2, 100.1],
    [0.3, 100.1],
    [0.2, 10.0],
    [0.9, 10.0],
    [0.9, 10.0],
    [0.8, 10.0],
    [0.8, 10.0],
])

def train_and_encode(data, n_centroids=256):
    """
    对每一维做 k-means 聚类，返回质心数组 + 编码结果
    """
    n_samples, n_dims = data.shape
    all_centroids = []
    encoded = np.zeros_like(data, dtype=np.int8)

    for d in range(n_dims):
        dim_data = data[:, d].reshape(-1, 1)
        k = min(n_centroids, len(dim_data))

        kmeans = KMeans(n_clusters=k, random_state=42, n_init="auto")
        kmeans.fit(dim_data)

        centroids = kmeans.cluster_centers_.flatten()
        codes = kmeans.predict(dim_data)

        all_centroids.append(centroids)
        encoded[:, d] = codes.astype(np.int8)

        print(f"维度 {d} 质心: {centroids.tolist()}")

    return all_centroids, encoded

def decode(encoded, centroids):
    """
    用质心数组把编码结果解码回 float32
    """
    n_samples, n_dims = encoded.shape
    decoded = np.zeros_like(encoded, dtype=np.float32)

    for d in range(n_dims):
        decoded[:, d] = [centroids[d][code] for code in encoded[:, d]]

    return decoded

# 编码
centroids, encoded_vectors = train_and_encode(data, n_centroids=256)
print("\n编码后的向量 (INT8):")
print(encoded_vectors)

# 解码
decoded_vectors = decode(encoded_vectors, centroids)
print("\n解码后的向量 (float32):")
print(decoded_vectors)
