import numpy as np


# 下面的注释统一使用这个 4 维 toy example 来说明数据如何沿着算法流动。
# 设 m = 2，则每个 4 维向量会被切成 2 个子空间，每个子空间维度 dsub = 2。
#
# 例子中的输入矩阵 X 可以写成：
# X = [
#   [1, 2, 3, 4],
#   [5, 6, 7, 8],
#   [9, 10, 11, 12],
# ]
# shape = (3, 4)
#
# 按 PQ 的切分方式：
# - 第 0 个子空间取前两列，得到 X[:, 0:2]
# - 第 1 个子空间取后两列，得到 X[:, 2:4]
#
# 因此：
# - X0 = [[1, 2], [5, 6], [9, 10]]，shape = (3, 2)
# - X1 = [[3, 4], [7, 8], [11, 12]]，shape = (3, 2)
#
# 后面的 train_pq / encode_pq / decode_pq / residual PQ 注释都沿用这套记法。


def sq_l2_dist_matrix(X, C):
    """Return squared L2 distance matrix: X (n, d), C (k, d) -> (n, k).

    Args:
        X: shape (n, d_local) 的样本矩阵。
            - 每一行是一个待比较的向量。
            - 在 direct PQ 中，X 可以是某个子空间切出来的 Xi。
            - 在 IVF 中，X 也可以是完整向量矩阵。
        C: shape (k, d_local) 的中心矩阵。
            - 每一行是一个聚类中心或码字。
            - 这里的 k 表示中心数量，不是向量维度。

    Returns:
        d2: shape (n, k) 的距离矩阵。
            d2[a, b] 表示第 a 个样本向量到第 b 个中心向量的平方 L2 距离。

    统一例子：
    - 若 X = [[1, 2], [5, 6], [9, 10]]，shape = (3, 2)
    - 若 C = [[1, 1], [8, 8]]，shape = (2, 2)
    - 返回 d2 shape = (3, 2)
    - d2[a, b] 表示第 a 个样本向量到第 b 个中心向量的平方 L2 距离
    """
    x2 = np.sum(X * X, axis=1, keepdims=True)
    c2 = np.sum(C * C, axis=1, keepdims=True).T
    xc = X @ C.T
    return x2 + c2 - 2.0 * xc


def kmeans(X, k, n_iter=30, seed=0):
    """Simple k-means for demonstration.

    Args:
        X: shape (n, d_local) 的样本矩阵。
            这里的 d_local 可以是完整维度 d，也可以是某个子空间维度 dsub。
            例如在 PQ 训练中，X 可能就是某个 Xi，像 [[1, 2], [5, 6], [9, 10]]。
        k: 聚类中心数量。
            - 返回结果中会得到 k 个中心。
            - 在 IVF 中，k 对应 coarse centroid 的个数，例如 nlist。
            - 在 PQ 的某个子空间中，k 也可以理解为该子空间码本里的码字数量。
        n_iter: k-means 的最大迭代轮数。
        seed: 随机种子，用于初始化中心。

    Returns:
        C: shape (k, d_local) 的聚类中心矩阵。
        assign: shape (n,) 的整数数组，assign[a] 是第 a 个样本所属的中心编号。
    """
    rng = np.random.default_rng(seed)
    n, _ = X.shape
    init_idx = rng.choice(n, size=k, replace=False)
    C = X[init_idx].copy()

    prev_assign = None
    assign = np.zeros(n, dtype=np.int32)
    for _ in range(n_iter):
        # d2: shape (n, k)
        # 每一行对应一个样本，每一列对应一个聚类中心。
        # 例如若 X = [[1, 2], [5, 6], [9, 10]] 且 k = 2，
        # 那么 d2[0] 会给出样本 [1, 2] 到两个中心的距离。
        d2 = sq_l2_dist_matrix(X, C)
        # assign: shape (n,)
        # assign[a] 是第 a 个样本当前被分到的中心编号。
        assign = np.argmin(d2, axis=1)

        if prev_assign is not None and np.array_equal(assign, prev_assign):
            break
        prev_assign = assign

        for j in range(k):
            # idx: shape (n_j,)
            # 存的是当前被分配到第 j 个中心的样本下标。
            idx = np.where(assign == j)[0]
            if len(idx) == 0:
                C[j] = X[rng.integers(0, n)]
            else:
                # X[idx]: shape (n_j, d_local)
                # 取出属于第 j 个簇的所有样本，再按列求平均，更新中心 C[j]。
                C[j] = np.mean(X[idx], axis=0)

    return C, assign


def train_pq(X, m=4, ksub=256, n_iter=25, seed=0):
    """Train product quantizer codebooks.

    Args:
        X: shape (n, d) 的训练向量矩阵。
            - n 表示样本数。
            - d 表示每个样本的原始特征维度。
            - 每一行是一个完整向量，例如原始向量或 residual 向量。
            - 若使用上面的 toy example，则 X 的 shape = (3, 4)。
        m: 子空间数量。会把 d 维向量均匀切成 m 段。
        ksub: 每个子空间的聚类中心数，即每个子量化器的码本大小。
        n_iter: k-means 迭代次数。
        seed: 随机种子。

    Returns:
        codebooks: 长度为 m 的列表。
            其中第 i 个元素 C 的 shape 为 (ksub, dsub)，表示第 i 个子空间
            的码本；每一行是该子空间中的一个聚类中心。
    """
    n, d = X.shape
    assert d % m == 0
    dsub = d // m
    codebooks = []

    for i in range(m):
        # Xi 的 shape 为 (n, dsub)。
        # 含义：从完整输入 X 中切出的第 i 段子向量矩阵。
        # - 行仍然对应原来的 n 个样本。
        # - 列只保留第 i 个子空间的 dsub 个维度。
        # 例如 X[j] 是第 j 个完整向量，则 Xi[j] 是它在第 i 个子空间上的切片。
        #
        # 用 4 维 toy example 说明：
        # X = [
        #   [1, 2, 3, 4],
        #   [5, 6, 7, 8],
        #   [9, 10, 11, 12],
        # ]，m = 2, dsub = 2
        #
        # 当 i = 0 时：Xi = X[:, 0:2]
        # Xi = [
        #   [1, 2],
        #   [5, 6],
        #   [9, 10],
        # ]
        #
        # 当 i = 1 时：Xi = X[:, 2:4]
        # Xi = [
        #   [3, 4],
        #   [7, 8],
        #   [11, 12],
        # ]
        #
        # 可以把它理解成：把每个完整向量 [x0, x1, x2, x3]
        # 拆成两个子向量 [x0, x1] 和 [x2, x3]，并对所有样本一起做这件事。
        Xi = X[:, i * dsub : (i + 1) * dsub]
        # C 的 shape 为 (ksub, dsub)，表示第 i 个子空间训练出来的码本。
        # 若 ksub = 2，则可以把 C 理解成这个子空间中的 2 个代表性中心。
        C, _ = kmeans(Xi, k=ksub, n_iter=n_iter, seed=seed + i)
        codebooks.append(C)

    return codebooks


def encode_pq(X, codebooks):
    """Encode vectors into PQ codes.

    Args:
        X: shape (n, d) 的待编码向量矩阵，每一行是一个完整向量。
            这里仍然沿用 train_pq 的同一套切分方式。
        codebooks: 长度为 m 的 PQ 码本列表；第 i 个码本 shape 为 (ksub, dsub)。
            其中 ksub 表示该子空间有码本中心/码字。

    Returns:
        codes: shape (n, m) 的整数矩阵。
            - 第 j 行表示第 j 个向量的 PQ 编码结果。
            - 第 i 列表示该向量在第 i 个子空间里选中的聚类中心编号。
    """
    n, d = X.shape
    m = len(codebooks)
    dsub = d // m
    codes = np.zeros((n, m), dtype=np.uint16)

    for i, C in enumerate(codebooks):
        # Xi: shape (n, dsub)，表示 X 在第 i 个子空间上的子向量矩阵。
        # 仍用 4 维例子：若某一行是 [1, 2, 3, 4]，则
        # - i = 0 时取到 [1, 2]
        # - i = 1 时取到 [3, 4]
        Xi = X[:, i * dsub : (i + 1) * dsub]
        # d2: shape (n, ksub)，d2[a, b] 表示
        # 第 a 个样本在第 i 个子空间的子向量 Xi[a] 与第 b 个码字 C[b]
        # 之间的平方 L2 距离。
        #
        # 如果第 0 个子空间中：
        # - Xi[a] = [1, 2]
        # - C = [[0, 1], [2, 2]]
        # 那么 d2[a] 会得到长度为 2 的距离数组，分别表示 [1, 2]
        # 到两个码字的距离；argmin 后选中的编号就是 codes[a, 0]。
        d2 = sq_l2_dist_matrix(Xi, C)
        codes[:, i] = np.argmin(d2, axis=1).astype(np.uint16)

    return codes


def decode_pq(codes, codebooks):
    """Decode PQ codes back to reconstructed vectors.

    Args:
        codes: shape (n, m) 的 PQ 编码矩阵。
            其中 codes[a, i] 是第 a 个样本在第 i 个子空间选中的码字编号。
        codebooks: 长度为 m 的 PQ 码本列表。

    Returns:
        Xhat: shape (n, d) 的重建向量矩阵。
            每一行是把 m 个子空间中选中的码字按顺序拼接后的近似向量。
    """
    n, m = codes.shape
    dsub = codebooks[0].shape[1]
    d = m * dsub
    Xhat = np.zeros((n, d), dtype=np.float32)

    for i, C in enumerate(codebooks):
        # C[codes[:, i]] 的 shape 为 (n, dsub)。
        # 含义：对第 i 个子空间，按 codes 中记录的中心编号，把对应码字取回来。
        #
        # 例如第 0 个样本 codes[0] = [1, 0]，则：
        # - 在子空间 0 取 codebooks[0][1]
        # - 在子空间 1 取 codebooks[1][0]
        # 再把这两个 dsub 维子向量拼接起来，得到该样本的重建向量。
        Xhat[:, i * dsub : (i + 1) * dsub] = C[codes[:, i]]

    return Xhat


def mse(a, b):
    """Return mean squared error between two matrices.

    Args:
        a: shape (n, d) 的真实向量矩阵。
        b: shape (n, d) 的重建向量矩阵。

    Returns:
        所有元素逐点平方误差的平均值。
    """
    return float(np.mean((a - b) ** 2))


def recall_at_k(db_true, db_approx, queries, k=10):
    """Average overlap recall@k.

    Args:
        db_true: shape (n_db, d) 的真实数据库向量。
        db_approx: shape (n_db, d) 的近似数据库向量。
        queries: shape (n_query, d) 的查询向量。
        k: 取前 k 个近邻做集合重叠比较。

    Returns:
        平均 recall@k。这里的定义是：
        真实 top-k 集合与近似 top-k 集合的交集大小，再除以 k，最后对所有 query 求平均。
    """
    hits = []
    for q in queries:
        # d_true / d_app: shape (n_db,)
        # 表示当前 query 到数据库中每个向量的距离。
        d_true = np.sum((db_true - q) ** 2, axis=1)
        d_app = np.sum((db_approx - q) ** 2, axis=1)
        # gt / pred: shape (k,)
        # 存储 top-k 最近邻对应的数据库下标。
        gt = np.argpartition(d_true, k)[:k]
        pred = np.argpartition(d_app, k)[:k]
        hits.append(len(set(gt.tolist()) & set(pred.tolist())) / k)
    return float(np.mean(hits))


def recall1(db_true, db_approx, queries):
    """Recall@1.

    Args:
        db_true: shape (n_db, d) 的真实数据库向量。
        db_approx: shape (n_db, d) 的近似数据库向量。
        queries: shape (n_query, d) 的查询向量。

    Returns:
        平均 recall@1，即最近邻是否命中的比例。
    """
    correct = 0
    for q in queries:
        d_true = np.sum((db_true - q) ** 2, axis=1)
        d_app = np.sum((db_approx - q) ** 2, axis=1)
        # np.argmin(...) 返回当前 query 最近邻在数据库中的下标。
        correct += int(int(np.argmin(d_true)) == int(np.argmin(d_app)))
    return correct / len(queries)


def main():
    """Run a direct-PQ vs residual-PQ toy experiment.

    流程概览：
    1. 生成训练集、数据库集、查询集
    2. 训练 direct PQ，并重建数据库向量
    3. 训练 coarse centroid，构造 residual，再训练 residual PQ
    4. 比较两种方案的 MSE、Recall@1、Recall@10
    """
    rng = np.random.default_rng(42)

    d = 16
    n_train = 30000
    n_db = 12000
    n_query = 400

    # Synthetic data: large global spread + small local noise
    n_true_clusters = 64
    center_scale = 60.0
    noise_sigma = 3.0
    # true_centers: shape (n_true_clusters, d)
    # 表示底层真实簇中心；后续所有样本都围绕这些中心加噪声生成。
    true_centers = rng.normal(0, center_scale, size=(n_true_clusters, d)).astype(np.float32)

    def sample_points(n):
        """Sample n synthetic vectors around true centers.

        Returns:
            X: shape (n, d) 的样本矩阵。
                每一行先随机选一个真实中心，再叠加高斯噪声得到。
        """
        cid = rng.integers(0, n_true_clusters, size=n)
        X = true_centers[cid] + rng.normal(0, noise_sigma, size=(n, d)).astype(np.float32)
        return X

    X_train = sample_points(n_train)
    X_db = sample_points(n_db)
    X_q = sample_points(n_query)

    print("Data generated")
    print(f"Raw vector std (global): {X_train.std():.4f}")

    # A) Direct PQ
    # 流程可以类比到 4 维 toy example：
    # 1. 用 X_train 训练码本，相当于先把每个 4 维向量切成两段
    # 2. 对 X_db 编码，得到每个子空间选中了哪个中心
    # 3. 再把这些中心拼回去，得到 X_db_hat_direct
    m = 4
    ksub = 256
    pq_direct = train_pq(X_train, m=m, ksub=ksub, n_iter=20, seed=123)
    # codes_direct: shape (n_db, m)
    # 对数据库中的每个原始向量直接做 PQ 编码。
    codes_direct = encode_pq(X_db, pq_direct)
    # X_db_hat_direct: shape (n_db, d)
    # 由 direct PQ 码字拼接出的数据库近似向量。
    X_db_hat_direct = decode_pq(codes_direct, pq_direct)

    # mse_direct / r1_direct / r10_direct
    # 分别评估 direct PQ 的重建误差和近邻检索质量。
    mse_direct = mse(X_db, X_db_hat_direct)
    r1_direct = recall1(X_db, X_db_hat_direct, X_q)
    r10_direct = recall_at_k(X_db, X_db_hat_direct, X_q, k=10)

    # B) IVF coarse + residual PQ
    # 与 Direct PQ 的区别是：不是直接对原始向量做 PQ，
    # 而是先找到 coarse centroid，再对 residual = 原向量 - 粗中心 做 PQ。
    nlist = 64
    # coarse_centroids: shape (nlist, d)
    # 这里的 nlist 就是 coarse quantizer 的中心数量。
    coarse_centroids, _ = kmeans(X_train, k=nlist, n_iter=30, seed=7)

    # train_assign: shape (n_train,)
    # 每个位置存储对应训练向量最近的 coarse centroid 编号。
    # 例如某个 4 维训练向量 x = [11, 19, 31, 39]，若最近粗中心 c = [10, 20, 30, 40]，
    # 则它的 train_assign 会记录 c 的编号。
    train_assign = np.argmin(sq_l2_dist_matrix(X_train, coarse_centroids), axis=1)
    # X_train_res: shape (n_train, d)
    # residual 向量 = 原向量 - 对应 coarse centroid。
    # 语义上表示样本相对粗量化中心的局部偏移，更适合再做 PQ。
    # 接上例：residual = [11, 19, 31, 39] - [10, 20, 30, 40] = [1, -1, 1, -1]。
    # 后续 train_pq(X_train_res, ...) 就是在这些 residual 向量上重复前面的切分、聚类流程。
    X_train_res = X_train - coarse_centroids[train_assign]
    print(f"Residual std after coarse quantization: {X_train_res.std():.4f}")

    pq_res = train_pq(X_train_res, m=m, ksub=ksub, n_iter=20, seed=999)

    # db_assign: shape (n_db,)
    # 存储数据库中每个向量所属的 coarse centroid 编号。
    db_assign = np.argmin(sq_l2_dist_matrix(X_db, coarse_centroids), axis=1)
    # X_db_res: shape (n_db, d)
    # 数据库向量减去对应 coarse centroid 后得到的 residual 矩阵。
    # 这些 residual 会被 encode_pq 编成 codes_res，格式与 direct PQ 完全一致，
    # 只是这里编码的对象从原始向量换成了 residual 向量。
    X_db_res = X_db - coarse_centroids[db_assign]
    codes_res = encode_pq(X_db_res, pq_res)

    # X_db_res_hat: shape (n_db, d)
    # 由 residual 的 PQ 编码重建出的 residual 近似值。
    X_db_res_hat = decode_pq(codes_res, pq_res)
    # X_db_hat_residual: shape (n_db, d)
    # 最终重建结果 = coarse centroid + residual 近似值。
    # 接上面的例子，若 residual 近似值被重建成 [0.8, -1.2, 0.9, -1.1]，
    # 那最终向量就是 [10, 20, 30, 40] + [0.8, -1.2, 0.9, -1.1]。
    X_db_hat_residual = coarse_centroids[db_assign] + X_db_res_hat

    # mse_res / r1_res / r10_res
    # 分别评估 residual PQ 的重建误差和近邻检索质量。
    mse_res = mse(X_db, X_db_hat_residual)
    r1_res = recall1(X_db, X_db_hat_residual, X_q)
    r10_res = recall_at_k(X_db, X_db_hat_residual, X_q, k=10)

    print("\n=== Evaluation ===")
    print(f"Direct PQ MSE:        {mse_direct:.6f}")
    print(f"Residual PQ MSE:      {mse_res:.6f}")
    print(f"MSE improvement:      {mse_direct / mse_res:.2f}x")

    print(f"\nDirect PQ Recall@1:   {r1_direct:.4f}")
    print(f"Residual PQ Recall@1: {r1_res:.4f}")

    print(f"\nDirect PQ Recall@10:   {r10_direct:.4f}")
    print(f"Residual PQ Recall@10: {r10_res:.4f}")


if __name__ == "__main__":
    main()
