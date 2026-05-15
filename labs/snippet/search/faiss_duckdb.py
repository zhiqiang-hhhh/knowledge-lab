import numpy as np
import faiss
import duckdb

# 配置参数
DIMENSION = 4  # 使用小维度便于观察
NUM_VECTORS = 10  # 少量向量便于观察
K = 3  # 返回的最近邻数量

def generate_normalized_data():
    """生成归一化的随机向量数据"""
    np.random.seed(42)
    vectors = np.random.random((NUM_VECTORS, DIMENSION)).astype('float32')
    
    # 归一化向量(内积相似度在归一化后等同于余弦相似度)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    
    # 创建一个固定查询向量便于观察
    query = np.array([0.9, 0.1, 0.2, 0.3], dtype='float32')
    query = query / np.linalg.norm(query)
    
    return vectors, query

def test_faiss_behavior(vectors, query):
    """测试Faiss库行为"""
    print("\n=== Faiss Behavior ===")
    
    # 创建内积索引
    index = faiss.IndexFlatIP(DIMENSION)
    index.add(vectors)
    
    # 搜索测试
    similarities, indices = index.search(query.reshape(1, -1), K)
    
    print("Faiss 返回结果:")
    for i in range(K):
        print(f"Top {i+1}: 向量 {indices[0][i]}, 相似度={similarities[0][i]:.4f}")

def test_duckdb_vss_behavior(vectors, query):
    """测试DuckDB VSS插件行为"""
    print("\n=== DuckDB VSS Behavior ===")
    
    # 创建DuckDB连接并加载VSS插件
    conn = duckdb.connect(database=':memory:')
    conn.execute("INSTALL 'vss';")
    conn.execute("LOAD 'vss';")
    
    # 创建表并建立VSS索引
    conn.execute("CREATE TABLE vectors (id INTEGER, vector FLOAT[4]);")
    
    # 插入数据
    for i, vec in enumerate(vectors):
        vec_list = [float(x) for x in vec]
        conn.execute(f"INSERT INTO vectors VALUES ({i}, {vec_list})")
    
    # 创建VSS索引 (使用内积作为距离度量)
    conn.execute("""
    CREATE VSS INDEX vss_idx ON vectors (vector) 
    USING 'IVF1,Flat'
    WITH (distance_type = 'dot');
    """)
    
    # 执行向量搜索
    query_list = [float(x) for x in query]
    result = conn.execute(f"""
    SELECT 
        id, 
        distance
    FROM (
        SELECT 
            id, 
            vector, 
            vss_distance(vector, {query_list}) as distance
        FROM vectors
    ) 
    ORDER BY distance ASC  -- 注意: VSS中dot距离是1-内积
    LIMIT {K};
    """).fetchall()
    
    print("DuckDB VSS 返回结果:")
    for rank, (idx, dist) in enumerate(result):
        # 将距离转换回内积相似度: similarity = 1 - distance
        print(f"Top {rank+1}: 向量 {idx}, 距离={dist:.4f}, 相似度={(1-dist):.4f}")
    
    conn.close()

def compare_core_behavior(vectors, query):
    """对比核心行为差异"""
    print("\n=== Core Behavior Comparison ===")
    
    # Faiss结果
    faiss_index = faiss.IndexFlatIP(DIMENSION)
    faiss_index.add(vectors)
    faiss_similarities, faiss_indices = faiss_index.search(query.reshape(1, -1), K)
    
    # DuckDB VSS结果
    conn = duckdb.connect(database=':memory:')
    conn.execute("INSTALL 'vss'; LOAD 'vss';")
    conn.execute("CREATE TABLE vectors (id INTEGER, vector FLOAT[4]);")
    for i, vec in enumerate(vectors):
        vec_list = [float(x) for x in vec]
        conn.execute(f"INSERT INTO vectors VALUES ({i}, {vec_list})")
    conn.execute("""
    CREATE VSS INDEX vss_idx ON vectors (vector) 
    USING 'IVF1,Flat' 
    WITH (distance_type = 'dot');
    """)
    vss_result = conn.execute(f"""
    SELECT id, vss_distance(vector, {[float(x) for x in query]}) as dist
    FROM vectors ORDER BY dist ASC LIMIT {K}
    """).fetchall()
    conn.close()
    
    # 对比结果
    print("\nTop K 结果对比:")
    print("Faiss 返回的向量ID:", faiss_indices[0])
    print("DuckDB VSS 返回的向量ID:", [row[0] for row in vss_result])
    
    print("\n相似度计算方式说明:")
    print("- Faiss: 直接返回内积相似度(越大越相似)")
    print("- DuckDB VSS: 返回的距离是 1 - 内积(越小越相似)")

def main():
    # 生成归一化的测试数据
    vectors, query = generate_normalized_data()
    
    print("=== 测试数据 ===")
    print("数据库向量(已归一化):")
    for i, vec in enumerate(vectors):
        print(f"向量 {i}: {np.round(vec, 4)}")
    print(f"\n查询向量: {np.round(query, 4)}")
    
    # 测试Faiss行为
    test_faiss_behavior(vectors, query)
    
    # 测试DuckDB VSS行为
    test_duckdb_vss_behavior(vectors, query)
    
    # 对比核心行为差异
    compare_core_behavior(vectors, query)
    
    print("\n=== 关键发现 ===")
    print("1. DuckDB VSS 插件提供了专门的向量搜索功能")
    print("2. VSS 使用距离度量(1 - 内积)，而Faiss直接使用内积")
    print("3. 两者在本质上计算相同的相似度，只是表示方式不同")
    print("4. VSS 支持多种索引类型(如IVF)和距离度量")
    print("5. VSS 结果需要将距离转换回相似度才能与Faiss直接比较")

if __name__ == "__main__":
    main()