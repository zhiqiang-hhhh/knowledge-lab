import numpy as np

def random_orthogonal(D):
    """生成一个 D×D 的随机正交矩阵（通过 QR 分解）"""
    A = np.random.randn(D, D)
    Q, R = np.linalg.qr(A)
    # 保证 Q 的方向统一（R 对角为正）
    diag = np.sign(np.diag(R))
    Q = Q * diag
    return Q

class RaBitQ1Bit:
    def __init__(self, D):
        self.D = D
        self.P = random_orthogonal(D)     # 随机正交矩阵 P
        self.center = None                 # 中心向量 c
        self.bits = None                   # N × D 的 bit 表示（0/1）
        self.bar_vectors = None            # quantized vectors \bar{o}
        self.norms = None                  # ∥o_r - c∥（变换后向量的模长）
        self.dot_corr = None               # ⟨\bar{o}, o_r - c⟩ 校正项

    def fit(self, X):
        """
        构建索引阶段：对 X 做量化、辅助项预计算
        X: np.ndarray, shape (N, D)
        """
        N, D = X.shape
        assert D == self.D

        # 1. 设定中心 c（这里取质心）
        self.center = np.mean(X, axis=0)

        # 2. 中心化 + 旋转变换
        #    o_r = (o - c) @ P  （这里 P 是正交矩阵）
        Xr = (X - self.center) @ self.P  # 维度 (N, D)

        # 3. 量化：对每个维度做 sign 判断
        bits = (Xr >= 0).astype(np.int8)  # 0/1 表示符号  
        # 构造 \bar{o}：+1/√D 或 -1/√D
        # bit == 1 对应 +1/√D， bit == 0 对应 -1/√D
        bar = bits * (1.0 / np.sqrt(D)) + (1 - bits) * ( -1.0 / np.sqrt(D) )

        # 4. 计算辅助项
        norms = np.linalg.norm(Xr, axis=1)  # 每个向量在变换后（中心化 + 旋转）的模长
        # ⟨\bar{o}, o_r - c⟩：即 bar 与 Xr 的点积
        dot_corr = np.sum(bar * Xr, axis=1)

        # 保存
        self.bits = bits
        self.bar_vectors = bar
        self.norms = norms
        self.dot_corr = dot_corr

    def estimate_distance_sq(self, q, idx):
        """
        对第 idx 个数据向量，估计其与查询 q 的 **平方距离**
        """
        D = self.D

        # 1. 对 query 做同样的中心化 + 旋转变换
        qr = (q - self.center) @ self.P  # 维度 (D,)

        # 2. query 也做量化（1-bit 版本）
        q_bits = (qr >= 0).astype(np.int8)
        q_bar = q_bits * (1.0 / np.sqrt(D)) + (1 - q_bits) * ( -1.0 / np.sqrt(D) )

        # 3. 估计内积 ⟨o_r - c, q_r⟩  
        #    使用一种简化估计：dot_corr[idx] * (q_bar · \bar{o}) / (⟨\bar{o}, o_r - c⟩)
        #    这个公式在真实 RaBitQ 中是有理论设计的，这里仅为演示。
        bar_o = self.bar_vectors[idx]
        est_inner = self.dot_corr[idx] * np.dot(q_bar, bar_o) / (self.dot_corr[idx] + 1e-9)

        # 4. 根据估计内积 + 辅助量得到估计距离
        #    d^2 ≈ ∥o_r - c∥^2 + ∥q_r∥^2 - 2 ⟨o_r - c, q_r⟩
        d2 = self.norms[idx]**2 + np.linalg.norm(qr)**2 - 2 * est_inner
        return d2

    def query(self, q, topk=5):
        """
        返回与 q 最近的 topk 向量（按估计距离排序）
        返回 (索引列表, 估计距离列表)
        """
        N = self.bits.shape[0]
        ests = [self.estimate_distance_sq(q, i) for i in range(N)]
        idxs = np.argsort(ests)
        return idxs[:topk], [ests[i] for i in idxs[:topk]]


# —— 测试一下 —— #
if __name__ == "__main__":
    np.random.seed(123)
    N, D = 200, 32
    X = np.random.randn(N, D)
    q = np.random.randn(D)

    model = RaBitQ1Bit(D)
    model.fit(X)
    topk_idx, topk_d2 = model.query(q, topk=3)
    print("Topk idx:", topk_idx)
    print("Estimated d2:", topk_d2)

    # 为了对比，算一下真实的 d2（使用原始向量）
    true_d2 = np.sum((X - q[None,:])**2, axis=1)
    print("True nearest:", np.argsort(true_d2)[:3])
    print("True d2:", sorted(true_d2)[:3])
