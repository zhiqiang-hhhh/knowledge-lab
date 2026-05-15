import numpy as np
from sklearn.cluster import KMeans
import time

def pq_train_and_eval(X, M, nbits):
    """ 在 Nxd 的矩阵 X 上做 PQ 训练+编码+解码 """
    N, d = X.shape
    subdim = d // M
    k = 2 ** nbits  # 每个子空间质心数
    
    centroids_list = []
    labels_list = []
    reconstructed = np.zeros_like(X)
    
    start = time.time()
    for m in range(M):
        subX = X[:, m*subdim:(m+1)*subdim]
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=5).fit(subX)
        centroids = kmeans.cluster_centers_
        labels = kmeans.predict(subX)
        
        centroids_list.append(centroids)
        labels_list.append(labels)
        reconstructed[:, m*subdim:(m+1)*subdim] = centroids[labels]
    end = time.time()
    
    mse = np.mean((X - reconstructed) ** 2)
    elapsed = end - start
    return mse, elapsed

# 实验参数
N, d = 1000, 128
X = np.random.randn(N, d).astype(np.float32)

nbits = 4   # 每个子空间 16 个质心
Ms = [1, 2, 4, 8, 16, 32, 64, 128]  # 子空间数量

print(f"数据规模: N={N}, d={d}, nbits={nbits}")
print("M (子空间数)\tMSE\t\t训练耗时(s)")

for M in Ms:
    mse, t = pq_train_and_eval(X, M, nbits)
    print(f"{M:3d}\t\t{mse:.4f}\t{t:.3f}")
