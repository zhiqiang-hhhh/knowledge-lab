#!/usr/bin/env python3
"""
简化版PQ参数M影响测试

快速测试不同M值对PQ性能的影响
"""

import numpy as np
import faiss
import time
import matplotlib.pyplot as plt

def quick_pq_test():
    """快速PQ测试函数"""
    # 参数设置
    dim = 64
    nb = 10000
    nq = 100
    k = 10
    
    print(f"快速PQ测试: dim={dim}, nb={nb}, nq={nq}")
    
    # 生成测试数据
    np.random.seed(42)
    database = np.random.randn(nb, dim).astype(np.float32)
    queries = np.random.randn(nq, dim).astype(np.float32)
    
    # 计算真值
    index_flat = faiss.IndexFlatL2(dim)
    index_flat.add(database)
    _, ground_truth = index_flat.search(queries, k)
    
    # 测试不同M值
    m_values = [1, 2, 4, 8, 16, 32]
    results = []
    
    for m in m_values:
        if dim % m != 0:
            continue
            
        print(f"Testing M={m}...")
        
        # 创建PQ索引
        index = faiss.IndexPQ(dim, m, 8, faiss.METRIC_L2)
        
        # 训练和添加
        start = time.time()
        index.train(database)
        index.add(database)
        build_time = time.time() - start
        
        # 搜索
        start = time.time()
        _, labels = index.search(queries, k)
        search_time = (time.time() - start) * 1000 / nq  # ms per query
        
        # 计算召回率
        recall = 0
        for i in range(nq):
            recall += len(set(labels[i]) & set(ground_truth[i])) / k
        recall /= nq
        
        results.append({
            'M': m,
            'sub_dim': dim // m,
            'build_time': build_time,
            'search_time': search_time,
            'recall': recall
        })
        
        print(f"  M={m}, 子维度={dim//m}, 构建时间={build_time:.3f}s, "
              f"搜索时间={search_time:.2f}ms, 召回率={recall:.3f}")
    
    # 绘图
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))
    
    ms = [r['M'] for r in results]
    sub_dims = [r['sub_dim'] for r in results]
    build_times = [r['build_time'] for r in results]
    search_times = [r['search_time'] for r in results]
    recalls = [r['recall'] for r in results]
    
    ax1.plot(ms, build_times, 'o-')
    ax1.set_xlabel('M (子量化器数量)')
    ax1.set_ylabel('构建时间 (秒)')
    ax1.set_title('M vs 构建时间')
    ax1.grid(True)
    
    ax2.plot(ms, search_times, 'o-', color='orange')
    ax2.set_xlabel('M (子量化器数量)')
    ax2.set_ylabel('搜索时间 (毫秒/查询)')
    ax2.set_title('M vs 搜索时间')
    ax2.grid(True)
    
    ax3.plot(ms, recalls, 'o-', color='green')
    ax3.set_xlabel('M (子量化器数量)')
    ax3.set_ylabel('召回率@10')
    ax3.set_title('M vs 召回率')
    ax3.grid(True)
    
    ax4.plot(sub_dims, recalls, 'o-', color='red')
    ax4.set_xlabel('子向量维度')
    ax4.set_ylabel('召回率@10')
    ax4.set_title('子向量维度 vs 召回率')
    ax4.grid(True)
    
    plt.tight_layout()
    plt.show()
    
    return results

if __name__ == "__main__":
    results = quick_pq_test()