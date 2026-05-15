import numpy as np

# 数据
vecs = np.array([
    [0.1, 0],
    [0.2, 100]
], dtype=np.float32)

n, d = vecs.shape
nbits = 8
nlevels = 2**nbits  # 256

def uniform_quantize_global(vecs, nlevels):
    """全局 min/max 量化"""
    vmin = vecs.min()
    vmax = vecs.max()
    scale = (vmax - vmin) / (nlevels - 1)
    codes = np.round((vecs - vmin) / scale).astype(np.int32)
    return codes, vmin, scale

def uniform_quantize_per_dim(vecs, nlevels):
    """逐维 min/max 量化"""
    vmin = vecs.min(axis=0)
    vmax = vecs.max(axis=0)
    scale = (vmax - vmin) / (nlevels - 1)
    codes = np.round((vecs - vmin) / scale).astype(np.int32)
    return codes, vmin, scale

def decode_global(codes, vmin, scale):
    """解码（全局量化）"""
    return vmin + codes * scale

def decode_per_dim(codes, vmin, scale):
    """解码（逐维量化）"""
    return vmin + codes * scale

# === 量化 + 解码 ===
codes_global, vmin_g, scale_g = uniform_quantize_global(vecs, nlevels)
recons_global = decode_global(codes_global, vmin_g, scale_g)

codes_perdim, vmin_d, scale_d = uniform_quantize_per_dim(vecs, nlevels)
recons_perdim = decode_per_dim(codes_perdim, vmin_d, scale_d)

# === 打印结果 ===
print("原始向量:")
print(vecs)

print("\n[全局 min/max 量化]")
print("编码结果:\n", codes_global)
print("解码结果:\n", recons_global)
print("误差:\n", vecs - recons_global)

print("\n[逐维 min/max 量化]")
print("编码结果:\n", codes_perdim)
print("解码结果:\n", recons_perdim)
print("误差:\n", vecs - recons_perdim)
