#!/usr/bin/env python3
"""
索引类型对比分析 Demo：IndexFlat、IndexHNSWFlat、IndexHNSWSQ、IndexHNSWPQ

对比内容（测试指标不变）：
1. 索引构建时间
2. 内存使用量（仅编码存储，忽略小量元数据，例如图连边）
3. 搜索速度
4. 召回率精度

作者: GitHub Copilot
日期: 2025-09-15
"""

import numpy as np
import faiss
import time
import matplotlib.pyplot as plt
import pandas as pd
from typing import List, Dict
import argparse
import warnings
warnings.filterwarnings('ignore')

# --- 日志前缀：为所有 print 增加 文件名:行号 前缀 ---
import builtins
import inspect
import os

_ORIG_PRINT = print

def _print_with_lineno(*args, sep=' ', end='\n', file=None, flush=False):
    """包装内置 print，在前面加上 [filename:lineno] 前缀。"""
    try:
        frame = inspect.currentframe()
        caller = frame.f_back if frame else None
        lineno = caller.f_lineno if caller else -1
        filename = os.path.basename(caller.f_code.co_filename) if caller else ''
        prefix = f"[{filename}:{lineno}] "
    except Exception:
        prefix = ''
    message = sep.join(str(a) for a in args)
    _ORIG_PRINT(prefix + message, end=end, file=file, flush=flush)

builtins.print = _print_with_lineno


class PQBenchmark:
    def __init__(self, dim: int = 128, nb: int = 65537, nq: int = 1000, k: int = 10):
        """
        初始化量化基准测试

        Args:
            dim: 向量维度
            nb: 数据库向量数量
            nq: 查询向量数量
            k: 搜索近邻数量
        """
        self.dim = dim
        self.nb = nb
        self.nq = nq
        self.k = k

        # 生成测试数据
        print(f"生成测试数据: dim={dim}, nb={nb:,}, nq={nq}")
        np.random.seed(42)
        self.database = np.random.randn(nb, dim).astype(np.float32)
        self.queries = np.random.randn(nq, dim).astype(np.float32)

        # 规范化向量（可选：为 L2 搜索带来更稳定的度量）
        faiss.normalize_L2(self.database)
        faiss.normalize_L2(self.queries)

        # 计算真实的最近邻（用于召回率计算）
        print("计算真实最近邻（用于召回率评估）...")
        self._compute_ground_truth()

    def _compute_ground_truth(self):
        """计算真实的最近邻作为召回率评估的基准"""
        index_flat = faiss.IndexFlatL2(self.dim)
        index_flat.add(self.database)
        _, self.ground_truth = index_flat.search(self.queries, self.k)

    # -------------------------------
    # 估算编码大小（bytes/向量）
    # -------------------------------
    def _pq_code_bytes_per_vec(self, m: int, nbits: int) -> float:
        return m * nbits / 8.0

    def _sq_code_bytes_per_vec(self, qtype: int) -> float:
        # 近似估算：按每维的码字大小
        QT = faiss.ScalarQuantizer
        if qtype == QT.QT_8bit or qtype == QT.QT_8bit_uniform or qtype == QT.QT_8bit_direct:
            return self.dim * 1.0
        if qtype == QT.QT_4bit:
            return self.dim * 0.5
        if qtype == QT.QT_fp16:
            return self.dim * 2.0
        # 兜底：按1字节/维
        return self.dim * 1.0

    def _flat_code_bytes_per_vec(self) -> float:
        return self.dim * 4.0

    # -------------------------------
    # 召回率计算
    # -------------------------------
    def _compute_recall(self, pred_labels: np.ndarray, true_labels: np.ndarray) -> float:
        """计算召回率"""
        assert pred_labels.shape == true_labels.shape
        nq, k = pred_labels.shape
        recall_sum = 0.0
        for i in range(nq):
            true_set = set(true_labels[i])
            pred_set = set(pred_labels[i])
            recall_sum += len(true_set.intersection(pred_set)) / len(true_set)
        return recall_sum / nq

    # -------------------------------
    # 各索引测试（基础与HNSW变体）
    # -------------------------------
    def _test_index_flat(self) -> Dict:
        """IndexFlat（无量化）"""
        index = faiss.IndexFlatL2(self.dim)

        start_time = time.time()
        index.add(self.database)
        add_time = time.time() - start_time
        build_time = add_time

        # 搜索
        start_time = time.time()
        distances, labels = index.search(self.queries, self.k)
        search_time = (time.time() - start_time) * 1e6 / self.nq  # μs per query

        # 召回率
        recall_1 = self._compute_recall(labels[:, :1], self.ground_truth[:, :1])
        recall_5 = self._compute_recall(labels[:, :5], self.ground_truth[:, :5])
        recall_10 = self._compute_recall(labels[:, :10], self.ground_truth[:, :10])

        code_bytes_per_vec = self._flat_code_bytes_per_vec()
        memory_usage_mb = self.nb * code_bytes_per_vec / (1024 * 1024)
        compression_ratio = (self.dim * 4.0) / code_bytes_per_vec  # 恒为 1

        return {
            'method': 'Flat',
            'params': 'Flat',
            'M': None,
            'nbits': None,
            'qtype': None,
            'hnsw_M': None,
            'efConstruction': None,
            'efSearch': None,
            'code_bytes_per_vec': code_bytes_per_vec,
            'compression_ratio': compression_ratio,
            'train_time': 0.0,
            'add_time': add_time,
            'build_time': build_time,
            'memory_usage_mb': memory_usage_mb,
            'search_time_us': search_time,
            'recall_at_1': recall_1,
            'recall_at_5': recall_5,
            'recall_at_10': recall_10
        }

    def _test_index_hnsw_flat(self, hnsw_M: int = 32, ef_construction: int = 200, ef_search: int = 64) -> Dict:
        """IndexHNSWFlat（HNSW 图 + float32 存储）"""
        index = faiss.IndexHNSWFlat(self.dim, hnsw_M)
        # 配置 HNSW 参数
        index.hnsw.efConstruction = ef_construction
        index.hnsw.efSearch = ef_search

        start_time = time.time()
        # HNSW Flat 不需要训练，直接 add
        index.add(self.database)
        add_time = time.time() - start_time
        build_time = add_time

        start_time = time.time()
        distances, labels = index.search(self.queries, self.k)
        search_time = (time.time() - start_time) * 1e6 / self.nq

        recall_1 = self._compute_recall(labels[:, :1], self.ground_truth[:, :1])
        recall_5 = self._compute_recall(labels[:, :5], self.ground_truth[:, :5])
        recall_10 = self._compute_recall(labels[:, :10], self.ground_truth[:, :10])

        code_bytes_per_vec = self._flat_code_bytes_per_vec()
        memory_usage_mb = self.nb * code_bytes_per_vec / (1024 * 1024)
        compression_ratio = (self.dim * 4.0) / code_bytes_per_vec

        return {
            'method': 'HNSW-Flat',
            'params': f'HNSW_M={hnsw_M}, efS={ef_search}',
            'M': None,
            'nbits': None,
            'qtype': None,
            'hnsw_M': hnsw_M,
            'efConstruction': ef_construction,
            'efSearch': ef_search,
            'code_bytes_per_vec': code_bytes_per_vec,
            'compression_ratio': compression_ratio,
            'train_time': 0.0,
            'add_time': add_time,
            'build_time': build_time,
            'memory_usage_mb': memory_usage_mb,
            'search_time_us': search_time,
            'recall_at_1': recall_1,
            'recall_at_5': recall_5,
            'recall_at_10': recall_10
        }

    def _test_index_pq(self, m: int, nbits: int) -> Dict:
        """IndexPQ（产品量化）"""
        index = faiss.IndexPQ(self.dim, m, nbits, faiss.METRIC_L2)

        # 训练和添加
        start_time = time.time()
        index.train(self.database)
        build_train = time.time() - start_time

        start_time = time.time()
        index.add(self.database)
        build_add = time.time() - start_time

        build_time = build_train + build_add

        # 搜索
        start_time = time.time()
        distances, labels = index.search(self.queries, self.k)
        search_time = (time.time() - start_time) * 1e6 / self.nq  # μs per query

        # 召回率
        recall_1 = self._compute_recall(labels[:, :1], self.ground_truth[:, :1])
        recall_5 = self._compute_recall(labels[:, :5], self.ground_truth[:, :5])
        recall_10 = self._compute_recall(labels[:, :10], self.ground_truth[:, :10])

        code_bytes_per_vec = self._pq_code_bytes_per_vec(m, nbits)
        memory_usage_mb = self.nb * code_bytes_per_vec / (1024 * 1024)
        compression_ratio = (self.dim * 4.0) / code_bytes_per_vec

        return {
            'method': 'PQ',
            'params': f'M={m}, nbits={nbits}',
            'M': m,
            'nbits': nbits,
            'qtype': None,
            'hnsw_M': None,
            'efConstruction': None,
            'efSearch': None,
            'code_bytes_per_vec': code_bytes_per_vec,
            'compression_ratio': compression_ratio,
            'train_time': build_train,
            'add_time': build_add,
            'build_time': build_time,
            'memory_usage_mb': memory_usage_mb,
            'search_time_us': search_time,
            'recall_at_1': recall_1,
            'recall_at_5': recall_5,
            'recall_at_10': recall_10
        }

    def _test_index_sq(self, qtype: int) -> Dict:
        """IndexSQ（标量量化）"""
        index = faiss.IndexScalarQuantizer(self.dim, qtype, faiss.METRIC_L2)

        # 训练（部分 qtype 需要训练，统一调用不影响）
        start_time = time.time()
        index.train(self.database)
        build_train = time.time() - start_time

        start_time = time.time()
        index.add(self.database)
        build_add = time.time() - start_time

        build_time = build_train + build_add

        # 搜索
        start_time = time.time()
        distances, labels = index.search(self.queries, self.k)
        search_time = (time.time() - start_time) * 1e6 / self.nq  # μs per query

        # 召回率
        recall_1 = self._compute_recall(labels[:, :1], self.ground_truth[:, :1])
        recall_5 = self._compute_recall(labels[:, :5], self.ground_truth[:, :5])
        recall_10 = self._compute_recall(labels[:, :10], self.ground_truth[:, :10])

        code_bytes_per_vec = self._sq_code_bytes_per_vec(qtype)
        memory_usage_mb = self.nb * code_bytes_per_vec / (1024 * 1024)
        compression_ratio = (self.dim * 4.0) / code_bytes_per_vec

        # qtype 名称
        QT = faiss.ScalarQuantizer
        qtype_name_map = {
            QT.QT_8bit: 'QT_8bit',
            QT.QT_4bit: 'QT_4bit',
            QT.QT_8bit_uniform: 'QT_8bit_uniform',
            QT.QT_fp16: 'QT_fp16',
            getattr(QT, 'QT_8bit_direct', -1): 'QT_8bit_direct'
        }
        qname = qtype_name_map.get(qtype, str(qtype))

        return {
            'method': 'SQ',
            'params': f'{qname}',
            'M': None,
            'nbits': None,
            'qtype': qname,
            'hnsw_M': None,
            'efConstruction': None,
            'efSearch': None,
            'code_bytes_per_vec': code_bytes_per_vec,
            'compression_ratio': compression_ratio,
            'train_time': build_train,
            'add_time': build_add,
            'build_time': build_time,
            'memory_usage_mb': memory_usage_mb,
            'search_time_us': search_time,
            'recall_at_1': recall_1,
            'recall_at_5': recall_5,
            'recall_at_10': recall_10
        }

    def _test_index_hnsw_sq(self, hnsw_M: int, qtype: int, ef_construction: int = 200, ef_search: int = 64) -> Dict:
        """IndexHNSWSQ（HNSW 图 + 标量量化）"""
        # 注意 SWIG 绑定签名：IndexHNSWSQ(d, qtype, M)
        index = faiss.IndexHNSWSQ(self.dim, qtype, hnsw_M)
        index.hnsw.efConstruction = ef_construction
        index.hnsw.efSearch = ef_search

        start_time = time.time()
        index.train(self.database)
        build_train = time.time() - start_time

        start_time = time.time()
        index.add(self.database)
        build_add = time.time() - start_time
        build_time = build_train + build_add

        start_time = time.time()
        distances, labels = index.search(self.queries, self.k)
        search_time = (time.time() - start_time) * 1e6 / self.nq

        recall_1 = self._compute_recall(labels[:, :1], self.ground_truth[:, :1])
        recall_5 = self._compute_recall(labels[:, :5], self.ground_truth[:, :5])
        recall_10 = self._compute_recall(labels[:, :10], self.ground_truth[:, :10])

        code_bytes_per_vec = self._sq_code_bytes_per_vec(qtype)
        memory_usage_mb = self.nb * code_bytes_per_vec / (1024 * 1024)
        compression_ratio = (self.dim * 4.0) / code_bytes_per_vec

        QT = faiss.ScalarQuantizer
        qtype_name_map = {
            QT.QT_8bit: 'QT_8bit',
            QT.QT_4bit: 'QT_4bit',
            QT.QT_8bit_uniform: 'QT_8bit_uniform',
            QT.QT_fp16: 'QT_fp16',
            getattr(QT, 'QT_8bit_direct', -1): 'QT_8bit_direct'
        }
        qname = qtype_name_map.get(qtype, str(qtype))

        return {
            'method': 'HNSW-SQ',
            'params': f'HNSW_M={hnsw_M}, {qname}, efS={ef_search}',
            'M': None,
            'nbits': None,
            'qtype': qname,
            'hnsw_M': hnsw_M,
            'efConstruction': ef_construction,
            'efSearch': ef_search,
            'code_bytes_per_vec': code_bytes_per_vec,
            'compression_ratio': compression_ratio,
            'train_time': build_train,
            'add_time': build_add,
            'build_time': build_time,
            'memory_usage_mb': memory_usage_mb,
            'search_time_us': search_time,
            'recall_at_1': recall_1,
            'recall_at_5': recall_5,
            'recall_at_10': recall_10
        }

    def _test_index_hnsw_pq(self, hnsw_M: int, m: int, nbits: int, ef_construction: int = 200, ef_search: int = 64) -> Dict:
        """IndexHNSWPQ（HNSW 图 + 产品量化）"""
        index = faiss.IndexHNSWPQ(self.dim, hnsw_M, m, nbits)
        index.hnsw.efConstruction = ef_construction
        index.hnsw.efSearch = ef_search

        # 训练 + 添加
        start_time = time.time()
        index.train(self.database)
        build_train = time.time() - start_time

        start_time = time.time()
        index.add(self.database)
        build_add = time.time() - start_time
        build_time = build_train + build_add

        # 搜索
        start_time = time.time()
        distances, labels = index.search(self.queries, self.k)
        search_time = (time.time() - start_time) * 1e6 / self.nq

        # 召回
        recall_1 = self._compute_recall(labels[:, :1], self.ground_truth[:, :1])
        recall_5 = self._compute_recall(labels[:, :5], self.ground_truth[:, :5])
        recall_10 = self._compute_recall(labels[:, :10], self.ground_truth[:, :10])

        code_bytes_per_vec = self._pq_code_bytes_per_vec(m, nbits)
        memory_usage_mb = self.nb * code_bytes_per_vec / (1024 * 1024)
        compression_ratio = (self.dim * 4.0) / code_bytes_per_vec

        return {
            'method': 'HNSW-PQ',
            'params': f'HNSW_M={hnsw_M}, PQ(M={m},nbits={nbits}), efS={ef_search}',
            'M': m,
            'nbits': nbits,
            'qtype': None,
            'hnsw_M': hnsw_M,
            'efConstruction': ef_construction,
            'efSearch': ef_search,
            'code_bytes_per_vec': code_bytes_per_vec,
            'compression_ratio': compression_ratio,
            'train_time': build_train,
            'add_time': build_add,
            'build_time': build_time,
            'memory_usage_mb': memory_usage_mb,
            'search_time_us': search_time,
            'recall_at_1': recall_1,
            'recall_at_5': recall_5,
            'recall_at_10': recall_10
        }

    # -------------------------------
    # 主测试入口
    # -------------------------------
    def test_index_types(
        self,
        hnsw_M: int = 32,
        ef_construction: int = 200,
        ef_search: int = 64,
        pq_m: int = 16,
        pq_nbits: int = 8,
        sq_qtype: int = None,
    ) -> pd.DataFrame:
        """
        对比四种索引：IndexFlat、IndexHNSWFlat、IndexHNSWSQ、IndexHNSWPQ
        - 测试指标不变（构建时间、编码内存、搜索时间、召回率）
        - HNSW 参数使用统一配置：M、efConstruction、efSearch
        - SQ/PQ 使用单点配置，便于直接对比不同索引类型
        """
        results = []

        print("\n开始测试 IndexFlat / IndexHNSWFlat / IndexHNSWSQ / IndexHNSWPQ")
        print("=" * 80)

        # IndexFlat
        try:
            print("\n测试 IndexFlat ...")
            res = self._test_index_flat()
            results.append(res)
            print(f"Flat 搜索时间: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}")
        except Exception as e:
            print(f"IndexFlat 测试失败: {e}")

        # IndexHNSWFlat
        try:
            print(f"\n测试 IndexHNSWFlat (M={hnsw_M}, efC={ef_construction}, efS={ef_search}) ...")
            res = self._test_index_hnsw_flat(hnsw_M, ef_construction, ef_search)
            results.append(res)
            print(f"HNSW-Flat 搜索: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}")
        except Exception as e:
            print(f"IndexHNSWFlat 测试失败: {e}")

        # IndexHNSWSQ（默认 SQ8）
        QT = faiss.ScalarQuantizer
        if sq_qtype is None:
            sq_qtype = QT.QT_8bit
        try:
            print(f"\n测试 IndexHNSWSQ (M={hnsw_M}, qtype={sq_qtype}, efC={ef_construction}, efS={ef_search}) ...")
            res = self._test_index_hnsw_sq(hnsw_M, sq_qtype, ef_construction, ef_search)
            results.append(res)
            print(f"HNSW-SQ 搜索: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}, 压缩比: {res['compression_ratio']:.1f}x")
        except Exception as e:
            print(f"IndexHNSWSQ 测试失败: {e}")

        # IndexHNSWPQ（默认 PQ(m=16, nbits=8)）
        if self.dim % pq_m != 0:
            print(f"跳过 HNSW-PQ: 维度{self.dim}不能被M={pq_m}整除")
        else:
            try:
                print(f"\n测试 IndexHNSWPQ (HNSW_M={hnsw_M}, PQ(M={pq_m}, nbits={pq_nbits}), efC={ef_construction}, efS={ef_search}) ...")
                res = self._test_index_hnsw_pq(hnsw_M, pq_m, pq_nbits, ef_construction, ef_search)
                results.append(res)
                print(f"HNSW-PQ 搜索: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}, 压缩比: {res['compression_ratio']:.1f}x")
            except Exception as e:
                print(f"IndexHNSWPQ 测试失败: {e}")

        return pd.DataFrame(results)

    def test_index_types_grid(
        self,
        hnsw_M_list: List[int],
        ef_construction: int,
        ef_search_list: List[int],
        pq_m_list: List[int],
        pq_nbits_list: List[int],
        sq_qtypes: List[int],
    ) -> pd.DataFrame:
        """
        批量对比：IndexFlat、IndexHNSWFlat(M,efS)、IndexHNSWSQ(M,efS,qtype)、IndexHNSWPQ(M,efS,PQ)
        - 采用笛卡尔组合作为网格：hnsw_M × ef_search × (sq_qtypes ∪ pq组合)
        - IndexFlat 只测一次，作为基线
        """
        results = []
        print("\n开始测试 IndexFlat / IndexHNSWFlat / IndexHNSWSQ / IndexHNSWPQ (Grid)")
        print("=" * 80)

        # Flat baseline
        try:
            res = self._test_index_flat()
            results.append(res)
            print(f"Flat 搜索时间: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}")
        except Exception as e:
            print(f"IndexFlat 测试失败: {e}")

        # HNSW sweeps
        for hM in hnsw_M_list:
            for efS in ef_search_list:
                # HNSW-Flat
                try:
                    print(f"\n测试 IndexHNSWFlat (M={hM}, efC={ef_construction}, efS={efS}) ...")
                    res = self._test_index_hnsw_flat(hM, ef_construction, efS)
                    results.append(res)
                    print(f"HNSW-Flat 搜索: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}")
                except Exception as e:
                    print(f"IndexHNSWFlat 测试失败: {e}")

                # HNSW-SQ for each qtype
                for qt in sq_qtypes:
                    try:
                        print(f"测试 IndexHNSWSQ (M={hM}, qtype={qt}, efC={ef_construction}, efS={efS}) ...")
                        res = self._test_index_hnsw_sq(hM, qt, ef_construction, efS)
                        results.append(res)
                        print(f"HNSW-SQ 搜索: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}, 压缩比: {res['compression_ratio']:.1f}x")
                    except Exception as e:
                        print(f"IndexHNSWSQ 测试失败: {e}")

                # HNSW-PQ for each PQ combo
                for m in pq_m_list:
                    if self.dim % m != 0:
                        print(f"跳过 HNSW-PQ: 维度{self.dim}不能被M={m}整除")
                        continue
                    for nbits in pq_nbits_list:
                        try:
                            print(f"测试 IndexHNSWPQ (HNSW_M={hM}, PQ(M={m}, nbits={nbits}), efC={ef_construction}, efS={efS}) ...")
                            res = self._test_index_hnsw_pq(hM, m, nbits, ef_construction, efS)
                            results.append(res)
                            print(f"HNSW-PQ 搜索: {res['search_time_us']:.1f}μs, 召回@10: {res['recall_at_10']:.3f}, 压缩比: {res['compression_ratio']:.1f}x")
                        except Exception as e:
                            print(f"IndexHNSWPQ 测试失败: {e}")

        return pd.DataFrame(results)

    # -------------------------------
    # 绘图与输出
    # -------------------------------
    def plot_results(self, results_df: pd.DataFrame, save_path: str = None):
        """绘制结果图表"""
        methods = results_df['method'].unique()
        colors = {
            'Flat': 'black',
            'HNSW-Flat': 'tab:green',
            'HNSW-SQ': 'tab:red',
            'HNSW-PQ': 'tab:purple',
            # 兼容旧方法
            'PQ': 'tab:blue',
            'SQ': 'tab:orange',
        }

        fig, axes = plt.subplots(1, 3, figsize=(20, 6))
        title = ' / '.join(methods)
        fig.suptitle(f'{title} 对比', fontsize=16, fontweight='bold')

        # 1. 压缩比（越大越省存储）
        for m in methods:
            df = results_df[results_df['method'] == m]
            axes[0].scatter(df['compression_ratio'], df['recall_at_10'], label=m, s=60, c=colors.get(m, None))
        axes[0].set_xlabel('压缩比 (float32占用 / 码本占用)')
        axes[0].set_ylabel('召回率@10')
        axes[0].set_title('压缩比 vs 召回率@10')
        axes[0].grid(True, alpha=0.3)
        axes[0].legend()

        # 2. 搜索时间
        for m in methods:
            df = results_df[results_df['method'] == m]
            axes[1].scatter(df['compression_ratio'], df['search_time_us'], label=m, s=60, c=colors.get(m, None))
        axes[1].set_xlabel('压缩比')
        axes[1].set_ylabel('搜索时间 (μs/query)')
        axes[1].set_title('压缩比 vs 搜索时间')
        axes[1].grid(True, alpha=0.3)

        # 3. 内存使用
        for m in methods:
            df = results_df[results_df['method'] == m]
            axes[2].scatter(df['compression_ratio'], df['memory_usage_mb'], label=m, s=60, c=colors.get(m, None))
        axes[2].set_xlabel('压缩比')
        axes[2].set_ylabel('内存使用 (MB)')
        axes[2].set_title('压缩比 vs 内存使用')
        axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存到: {save_path}")
        plt.show()

    def print_analysis_summary(self, results_df: pd.DataFrame):
        """打印分析总结"""
        print("\n" + "=" * 80)
        title = ' / '.join(results_df['method'].unique())
        print(f"{title} 对比分析总结")
        print("=" * 80)

        # 找到若干代表性最优点
        try:
            best_recall = results_df.loc[results_df['recall_at_10'].idxmax()]
            fastest = results_df.loc[results_df['search_time_us'].idxmin()]
            best_compress = results_df.loc[results_df['compression_ratio'].idxmax()]
            print(f"   🎯 最高召回: {best_recall['method']}({best_recall['params']}) 召回@10={best_recall['recall_at_10']:.3f}")
            print(f"   ⚡ 最快搜索: {fastest['method']}({fastest['params']}) 时间={fastest['search_time_us']:.1f}μs")
            print(f"   💾 最大压缩: {best_compress['method']}({best_compress['params']}) 压缩比={best_compress['compression_ratio']:.1f}x")
        except Exception:
            pass

        cols = ['method', 'params', 'compression_ratio', 'memory_usage_mb', 'train_time', 'add_time', 'build_time', 'search_time_us', 'recall_at_10']
        print("\n详细结果（部分列）：")
        print(results_df[cols].sort_values(['method', 'params']).to_string(index=False))

    # -------------------------------
    # PQ / SQ 单独测试入口
    # -------------------------------
    def test_pq_grid(self, pq_m_values: List[int], pq_nbits_values: List[int], include_flat: bool = True) -> pd.DataFrame:
        """仅测试 IndexPQ 参数网格，可选包含 Flat 基线"""
        results = []
        if include_flat:
            try:
                res = self._test_index_flat()
                results.append(res)
                print(f"Flat: 搜索 {res['search_time_us']:.1f}μs, R@10 {res['recall_at_10']:.3f}")
            except Exception as e:
                print(f"Flat 测试失败: {e}")

        print("\n测试 IndexPQ 参数网格 ...")
        for m in pq_m_values:
            if self.dim % m != 0:
                print(f"跳过 M={m}: 维度{self.dim}不能被M整除")
                continue
            for nbits in pq_nbits_values:
                try:
                    res = self._test_index_pq(m, nbits)
                    results.append(res)
                    print(f"PQ(M={m}, nbits={nbits}): 搜索 {res['search_time_us']:.1f}μs, R@10 {res['recall_at_10']:.3f}, 压缩比 {res['compression_ratio']:.1f}x")
                except Exception as e:
                    print(f"PQ(M={m}, nbits={nbits}) 测试失败: {e}")
        return pd.DataFrame(results)

    def test_sq_types(self, sq_qtypes: List[int], include_flat: bool = True) -> pd.DataFrame:
        """仅测试 IndexSQ 多种 qtype，可选包含 Flat 基线"""
        results = []
        if include_flat:
            try:
                res = self._test_index_flat()
                results.append(res)
                print(f"Flat: 搜索 {res['search_time_us']:.1f}μs, R@10 {res['recall_at_10']:.3f}")
            except Exception as e:
                print(f"Flat 测试失败: {e}")

        print("\n测试 IndexSQ 多种量化类型 ...")
        for qt in sq_qtypes:
            try:
                res = self._test_index_sq(qt)
                results.append(res)
                print(f"SQ({res['params']}): 搜索 {res['search_time_us']:.1f}μs, R@10 {res['recall_at_10']:.3f}, 压缩比 {res['compression_ratio']:.1f}x")
            except Exception as e:
                print(f"SQ(qtype={qt}) 测试失败: {e}")
        return pd.DataFrame(results)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Faiss 索引基准测试')
    parser.add_argument('--mode', choices=['index_types', 'pq', 'sq'], default='index_types', help='选择测试模式')
    parser.add_argument('--dim', type=int, default=128)
    parser.add_argument('--nb', type=int, default=50000)
    parser.add_argument('--nq', type=int, default=1000)
    parser.add_argument('--k', type=int, default=10)

    # HNSW params
    parser.add_argument('--hnsw-M', dest='hnsw_M', type=str, default='32', help='HNSW 的 M，支持逗号分隔: 16,32')
    parser.add_argument('--efC', dest='ef_construction', type=int, default=200)
    parser.add_argument('--efS', dest='ef_search', type=str, default='64', help='HNSW 的 efSearch，支持逗号分隔: 32,64,128')

    # PQ params
    parser.add_argument('--pq-m', dest='pq_m', type=str, default='16', help='HNSW-PQ 用的 m 或 PQ 单测默认 m；支持逗号分隔如: 4,16,32')
    parser.add_argument('--pq-nbits', dest='pq_nbits', type=str, default='8', help='HNSW-PQ 用的 nbits 或 PQ 单测默认 nbits；支持逗号分隔如: 4,8')
    parser.add_argument('--pq-m-grid', dest='pq_m_grid', type=int, nargs='+', default=None, help='PQ 单测的 M 网格，如: --pq-m-grid 4 16 32')
    parser.add_argument('--pq-nbits-grid', dest='pq_nbits_grid', type=int, nargs='+', default=None, help='PQ 单测的 nbits 网格，如: --pq-nbits-grid 4 8')

    # SQ params
    parser.add_argument('--sq-qtypes', dest='sq_qtypes', nargs='+', default=None, help='SQ 单测的 qtypes，可用名称: QT_8bit, QT_4bit, QT_8bit_uniform, QT_fp16, QT_8bit_direct')

    args = parser.parse_args()

    # 初始化基准测试
    benchmark = PQBenchmark(dim=args.dim, nb=args.nb, nq=args.nq, k=args.k)

    def _parse_csv_ints(val: str) -> list:
        if val is None:
            return []
        parts = []
        for token in str(val).split(','):
            token = token.strip()
            if token == '':
                continue
            if not token.lstrip('-').isdigit():
                raise ValueError(f"期望整数列表，得到: {val}")
            parts.append(int(token))
        return parts

    if args.mode == 'index_types':
        print("🚀 索引类型对比分析（IndexFlat / IndexHNSWFlat / IndexHNSWSQ / IndexHNSWPQ）")
        print("=" * 80)
        # 解析参数列表
        hnsw_M_list = _parse_csv_ints(args.hnsw_M) or [32]
        ef_search_list = _parse_csv_ints(args.ef_search) or [64]
        pq_m_list = _parse_csv_ints(args.pq_m) or [16]
        pq_nbits_list = _parse_csv_ints(args.pq_nbits) or [8]
        # SQ qtypes：沿用 sq 模式的解析逻辑
        QT = faiss.ScalarQuantizer
        name_to_qt = {
            'QT_8bit': getattr(QT, 'QT_8bit', 0),
            'QT_4bit': getattr(QT, 'QT_4bit', 1),
            'QT_8bit_uniform': getattr(QT, 'QT_8bit_uniform', 2),
            'QT_fp16': getattr(QT, 'QT_fp16', 3),
            'QT_8bit_direct': getattr(QT, 'QT_8bit_direct', None),
        }
        # 默认只测 SQ8
        sq_qtypes = [name_to_qt['QT_8bit']]
        # 如果用户通过 --sq-qtypes 传了值，则覆盖默认
        if args.sq_qtypes is not None:
            sq_qtypes = []
            for token in args.sq_qtypes:
                for sub in str(token).split(','):
                    sub = sub.strip()
                    if sub == '':
                        continue
                    if sub.isdigit():
                        sq_qtypes.append(int(sub))
                    else:
                        qt_val = name_to_qt.get(sub)
                        if qt_val is not None:
                            sq_qtypes.append(qt_val)
            sq_qtypes = [qt for qt in sq_qtypes if qt is not None]

        # 运行网格测试
        print(f"HNSW_M: {hnsw_M_list}  | efC: {args.ef_construction}  | efS: {ef_search_list}")
        print(f"HNSW-PQ: M={pq_m_list}, nbits={pq_nbits_list}  | HNSW-SQ qtypes: {sq_qtypes}")
        results_df = benchmark.test_index_types_grid(
            hnsw_M_list=hnsw_M_list,
            ef_construction=args.ef_construction,
            ef_search_list=ef_search_list,
            pq_m_list=pq_m_list,
            pq_nbits_list=pq_nbits_list,
            sq_qtypes=sq_qtypes,
        )
        out_csv = 'index_types_benchmark_results.csv'
        out_png = 'index_types_benchmark_analysis.png'

    elif args.mode == 'pq':
        print("🚀 PQ 单独测试（IndexPQ 参数网格）")
        print("=" * 80)
        pq_m_values = args.pq_m_grid if args.pq_m_grid else _parse_csv_ints(args.pq_m)
        pq_nbits_values = args.pq_nbits_grid if args.pq_nbits_grid else _parse_csv_ints(args.pq_nbits)
        if not pq_m_values:
            pq_m_values = [16]
        if not pq_nbits_values:
            pq_nbits_values = [8]
        print(f"PQ M 值: {pq_m_values}")
        print(f"PQ nbits 值: {pq_nbits_values}")
        results_df = benchmark.test_pq_grid(pq_m_values, pq_nbits_values, include_flat=True)
        out_csv = 'pq_benchmark_results.csv'
        out_png = 'pq_benchmark_analysis.png'

    else:  # sq
        print("🚀 SQ 单独测试（IndexSQ 多 qtype）")
        print("=" * 80)
        QT = faiss.ScalarQuantizer
        name_to_qt = {
            'QT_8bit': getattr(QT, 'QT_8bit', 0),
            'QT_4bit': getattr(QT, 'QT_4bit', 1),
            'QT_8bit_uniform': getattr(QT, 'QT_8bit_uniform', 2),
            'QT_fp16': getattr(QT, 'QT_fp16', 3),
            'QT_8bit_direct': getattr(QT, 'QT_8bit_direct', None),
        }
        if args.sq_qtypes is None:
            sq_qtypes = [name_to_qt['QT_8bit'], name_to_qt['QT_4bit']]
        else:
            sq_qtypes = []
            for token in args.sq_qtypes:
                for sub in str(token).split(','):
                    sub = sub.strip()
                    if sub == '':
                        continue
                    if sub.isdigit():
                        sq_qtypes.append(int(sub))
                    else:
                        qt_val = name_to_qt.get(sub)
                        if qt_val is not None:
                            sq_qtypes.append(qt_val)
        sq_qtypes = [qt for qt in sq_qtypes if qt is not None]
        print(f"SQ qtypes: {sq_qtypes}")
        results_df = benchmark.test_sq_types(sq_qtypes, include_flat=True)
        out_csv = 'sq_benchmark_results.csv'
        out_png = 'sq_benchmark_analysis.png'

    # 保存结果与图表、总结
    results_df.to_csv(out_csv, index=False)
    print(f"\n💾 结果已保存到: {out_csv}")
    benchmark.plot_results(results_df, out_png)
    benchmark.print_analysis_summary(results_df)
    print(f"\n✅ 分析完成！")


if __name__ == "__main__":
    main()
