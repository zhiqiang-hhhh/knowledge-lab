import numpy as np

class ScalarQuantizer:
    def __init__(self, bits=8):
        self.bits = bits
        self.max_code = 2**bits - 1
        self.mins = None
        self.scales = None

    def fit(self, X):
        """
        X: (n, d) 浮点训练数据
        """
        self.mins = X.min(axis=0)
        maxs = X.max(axis=0)
        self.scales = (maxs - self.mins) / self.max_code
        self.scales[self.scales == 0] = 1e-8  # 防止除零

    def encode(self, X):
        """
        把浮点向量编码为量化后的 code (uint8)
        """
        codes = np.round((X - self.mins) / self.scales).astype(np.int32)
        codes = np.clip(codes, 0, self.max_code).astype(np.uint8)
        return codes

    def decode(self, codes):
        """
        解码回浮点数（一般不用于距离计算）
        """
        return self.mins + codes.astype(np.float32) * self.scales

    def build_lut(self, query, debug=False):
        """
        构建查询向量的 LUT
        query: (d,) 浮点查询向量
        返回: LUT, shape=(d, 256)
        """
        d = query.shape[0]
        LUT = np.zeros((d, self.max_code + 1), dtype=np.float32)
        for j in range(d):
            q_val = query[j]
            code_vals = self.mins[j] + np.arange(0, self.max_code + 1) * self.scales[j]
            LUT[j, :] = (q_val - code_vals) ** 2

            if debug and j < 2:  # 只打印前两维，避免太多信息
                print(f"\n=== 维度 {j} ===")
                print(f"query[{j}] = {q_val:.4f}")
                print(f"mins[{j}] = {self.mins[j]:.4f}, scale[{j}] = {self.scales[j]:.4f}")
                print("code_vals[:10] =", np.round(code_vals[:10], 4))  # 前10个候选值
                print("LUT[j, :10]   =", np.round(LUT[j, :10], 4))     # 前10个平方差
        return LUT


    def distance(self, query, db_codes, LUT):
        """
        用 LUT 查表计算距离
        query: (d,) 浮点查询向量
        db_codes: (n, d) 数据库编码
        LUT: (d, 256) 查找表
        返回: (n,) 距离
        """
        n, d = db_codes.shape
        dist = np.zeros(n, dtype=np.float32)
        for i in range(n):
            # 按维查表累加
            dist[i] = LUT[np.arange(d), db_codes[i]].sum()
        return dist


# ==== Demo ====
np.random.seed(123)

# 数据库有 1000 个向量，每个 32 维
X = np.random.randn(1000, 32).astype(np.float32)
query = np.random.randn(32).astype(np.float32)

# 训练量化器
sq = ScalarQuantizer(bits=8)
sq.fit(X)

# 数据库编码
db_codes = sq.encode(X)

# 构建查询的 LUT
LUT = sq.build_lut(query, debug=True)

# 1. 用 LUT 查表计算距离
dist_lut = sq.distance(query, db_codes, LUT)

# 2. 用原始浮点计算距离 (baseline)
dist_float = np.sum((X - query) ** 2, axis=1)

# 对比误差
print("平均误差:", np.mean(np.abs(dist_lut - dist_float)))
print("前 5 个距离 (LUT):", dist_lut[:5])
print("前 5 个距离 (Float):", dist_float[:5])
