# Annotation Style

Use this skill when you need to add explanatory comments to algorithmic code.

It is the single merged annotation skill for this project. It covers both:
- general array-heavy algorithm annotations
- PQ / IVF / residual-PQ specific teaching annotations

## Goal

Write comments that make code easier to reason about, especially when variables carry
non-obvious mathematical or data-layout meaning.

The comments should help a reader understand:
- what each important variable or array represents
- the shape of each array or matrix
- what each axis means
- how slicing, indexing, aggregation, or reconstruction changes the data
- how intermediate results connect to the next step
- one small running example when the logic is not obvious

## Global Rules

1. Prefer `shape + semantic meaning` together.
   - Good: `scores: shape (n_query, n_db), each row is one query against all db items`
   - Bad: `scores is a matrix`

2. Explain transformations in algorithm order.
   - input -> derived array -> assignment/selection -> reconstruction/output

3. State axis meaning explicitly.
   - Explain what rows, columns, heads, channels, or time steps represent.
   - If code uses `axis=0` or `axis=1`, explain what is being reduced.

4. Explain slicing and indexing precisely.
   - Clarify whether slicing is by rows, columns, subspaces, channels, etc.
   - Explain advanced indexing like `X[idx]` or `C[codes[:, i]]`.

5. Use one running example when helpful.
   - Reuse the same example across nearby functions.
   - Do not switch examples mid-pipeline unless necessary.

6. Focus on reasoning-heavy lines.
   - Comment shape-changing operations, score/distance matrices, assignments, residuals, reconstruction.
   - Skip obvious syntax-only comments.

7. Keep terminology stable.
   - If `X` means full input matrix once, keep that meaning everywhere.
   - If `scores[i, j]` means query `i` vs candidate `j`, do not redefine it later.

## Part A: General Array Algorithm Style

Use this style for:
- matrix/tensor slicing and indexing
- clustering, retrieval, masking, scoring, aggregation
- DP tables, attention-like scores, adjacency matrices
- numeric pipelines where array semantics are easy to lose

### General Workflow

1. Identify core arrays.
   - Typical names: `X`, `Y`, `scores`, `dist`, `mask`, `assign`, `idx`, `codes`, `centers`, `state`

2. Define a tiny example if needed.
   - Prefer examples like `(3, 4)` matrices or `2 x 3` score tables.

3. Add comments in dataflow order.
   - input arrays
   - intermediate arrays
   - selected indices or assignments
   - final outputs

### General Comment Patterns

```python
# X: shape (n, d)
# 每一行是一个样本向量。

# scores: shape (n_query, n_db)
# scores[i, j] 表示第 i 个 query 与第 j 个候选项之间的分数。

# idx: shape (n_selected,)
# 存储被选中元素在原数组中的下标。

# X_sub = X[:, l:r]
# 按列切片，保留所有行，只取第 l 到 r-1 列。

# X[idx]: shape (n_selected, d)
# 用下标数组从 X 中取出若干行。

# np.mean(X, axis=0)
# 按列求平均；结果仍表示一个 d 维向量。
```

## Part B: PQ / IVF / Residual-PQ Style

Use this style for:
- product quantization
- IVF coarse quantization
- residual quantization
- subspace slicing, codebooks, codes, and reconstruction

### PQ-Specific Rules

1. Prefer one fixed toy example across the whole code path.
   - Recommended: 4-D vectors split into 2 subspaces.

2. Keep naming consistent across functions.
   - `X`: full vector matrix or residual matrix
   - `Xi`: the i-th subspace slice from `X`
   - `C`: codebook / centroids
   - `d2`: squared distance matrix
   - `codes`: selected codeword ids
   - `Xhat`: reconstructed vectors

3. Explain the full PQ pipeline in order.
   - full vectors -> subspace slices -> distances -> codes -> reconstruction
   - for residual pipelines: original vector -> coarse centroid -> residual -> residual code -> final reconstruction

### Recommended PQ Example

```python
X = np.array([
    [1, 2, 3, 4],
    [5, 6, 7, 8],
    [9, 10, 11, 12],
])
```

If `m = 2`, then `dsub = 2` and:
- `X[:, 0:2]` is the first subspace
- `X[:, 2:4]` is the second subspace

### PQ Comment Patterns

```python
# X: shape (n, d)
# 每一行是一个完整向量。下面统一用 4 维例子说明。

# Xi: shape (n, dsub)
# 表示从 X 中按列切出的第 i 个子空间。
Xi = X[:, i * dsub : (i + 1) * dsub]

# d2: shape (n, ksub)
# d2[a, b] 表示第 a 个样本子向量到第 b 个码字的平方 L2 距离。
d2 = sq_l2_dist_matrix(Xi, C)

# codes: shape (n, m)
# codes[a, i] 是第 a 个样本在第 i 个子空间里选中的码字编号。
codes[:, i] = np.argmin(d2, axis=1)

# X_res: shape (n, d)
# residual = 原向量 - 对应 coarse centroid。
X_res = X - coarse_centroids[assign]

# X_hat: shape (n, d)
# 最终重建 = coarse centroid + residual 近似值。
X_hat = coarse_centroids[assign] + X_res_hat
```

## When To Use A Running Example

Use a concrete example if:
- slicing is non-obvious
- the same symbol changes meaning easily
- reconstruction depends on indices or codes
- residuals, masks, or score matrices are involved

## Quality Bar

A good result should let a reader answer:
- each important variable's shape and meaning
- what each axis stands for
- how one line transforms the previous result
- what indices, assignments, or codes refer to
- how the final output is assembled

## How To Invoke Manually

Examples:

`使用 Annotation Style skill，给这个文件补充 shape、轴语义、数组变换过程注释。`

`按 Annotation Style 的 PQ 部分规范，给 IVF/PQ 代码补一套统一 4 维例子的教学型注释。`
