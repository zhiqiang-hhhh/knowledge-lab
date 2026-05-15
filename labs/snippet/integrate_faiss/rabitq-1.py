import numpy as np

# =========================
# 1. 准备数据
# =========================
o_r = np.array([3.0, 4.0])   # 数据向量
q_r = np.array([2.0, 0.0])   # 查询向量
c   = np.array([1.0, 2.0])   # 质心

# =========================
# 2. 以质心为中心
# =========================
o_centered = o_r - c
q_centered = q_r - c

# =========================
# 3. 范数与单位向量
# =========================
norm_o = np.linalg.norm(o_centered)
norm_q = np.linalg.norm(q_centered)
o = o_centered / norm_o
q = q_centered / norm_q

# =========================
# 4. 单位向量内积
# =========================
inner_product = np.dot(q, o)

# =========================
# 5. 直接计算原始欧氏距离平方
# =========================
euclid_sq = np.linalg.norm(o_r - q_r)**2

# =========================
# 6. 使用公式计算
# =========================
formula_sq = norm_o**2 + norm_q**2 - 2 * norm_o * norm_q * inner_product

print("o_r - c =", o_centered)
print("q_r - c =", q_centered)
print("||o_r - c|| =", norm_o)
print("||q_r - c|| =", norm_q)
print("Unit o =", o)
print("Unit q =", q)
print("Inner product <q,o> =", inner_product)
print("Euclidean distance squared (direct) =", euclid_sq)
print("Formula result =", formula_sq)
