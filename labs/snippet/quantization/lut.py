import numpy as np

class SimpleSQ4bit:
    def __init__(self, bits=4):
        self.bits = bits
        self.max_code = (1 << bits) - 1  # 15
        self.mins = None
        self.scales = None

    def train(self, x_train):
        # 假设 x_train shape = (n, d)
        self.mins = x_train.min(axis=0)
        self.maxs = x_train.max(axis=0)
        self.scales = (self.maxs - self.mins) / self.max_code

        print("训练完毕: ")
        for j in range(x_train.shape[1]):
            print(f"  维度 {j}: min={self.mins[j]:.4f}, max={self.maxs[j]:.4f}, scale={self.scales[j]:.4f}")

    def build_LUT(self, query):
        d = len(query)
        LUT = np.zeros((d, self.max_code + 1))
        for j in range(d):
            q_val = query[j]
            code_vals = self.mins[j] + np.arange(0, self.max_code + 1) * self.scales[j]

            # Debug 输出
            print(f"\n维度 {j} 查询值 q_val = {q_val:.4f}")
            print(f"code_vals (所有可能解码值): {np.round(code_vals, 4)}")
            print(f"(q_val - code_vals)^2: {np.round((q_val - code_vals) ** 2, 4)}")

            LUT[j, :] = (q_val - code_vals) ** 2
        return LUT

# ==== Demo ====
if __name__ == "__main__":
    # 构造训练数据 (5个点，2维)
    x_train = np.array([
        [-1.0, 0.0],
        [-0.5, 0.2],
        [0.0, 0.5],
        [0.7, -0.3],
        [1.0, 1.0]
    ])

    sq = SimpleSQ4bit(bits=4)
    sq.train(x_train)

    # 构造查询向量
    query = np.array([0.3, 0.7])
    LUT = sq.build_LUT(query)

    print("\n最终 LUT：")
    print(np.round(LUT, 4))
