from pymilvus import connections

connections.connect(
    alias="default",
    host="127.0.0.1",
    port="19530"
)

print("connected to milvus")


from pymilvus import (
    FieldSchema, CollectionSchema, DataType, Collection, utility
)

COLLECTION_NAME = "diskann_demo"
DIM = 128

# 如果已存在，先删
if utility.has_collection(COLLECTION_NAME):
    utility.drop_collection(COLLECTION_NAME)

fields = [
    FieldSchema(
        name="id",
        dtype=DataType.INT64,
        is_primary=True,
        auto_id=False
    ),
    FieldSchema(
        name="embedding",
        dtype=DataType.FLOAT_VECTOR,
        dim=DIM
    )
]

schema = CollectionSchema(
    fields,
    description="milvus diskann demo"
)

collection = Collection(
    name=COLLECTION_NAME,
    schema=schema
)

print("collection created")


import numpy as np

N = 100_000   # demo 用 10 万，生产可到千万 / 亿
np.random.seed(42)

ids = list(range(N))
vectors = np.random.random((N, DIM)).astype("float32")

collection.insert([ids, vectors])
collection.flush()

print("data inserted")


index_params = {
    "index_type": "DISKANN",
    "metric_type": "L2",
    "params": {
        # DiskANN 图参数
        "graph_degree": 64,
        "search_list_size": 100,
        # 构建并行
        "build_thread_num": 8
    }
}

collection.create_index(
    field_name="embedding",
    index_params=index_params
)

print("diskann index built")


collection.load()
print("collection loaded")


search_params = {
    "metric_type": "L2",
    "params": {
        # 查询阶段最重要参数
        "search_list_size": 64
    }
}

query = np.random.random((5, DIM)).astype("float32")

results = collection.search(
    data=query,
    anns_field="embedding",
    param=search_params,
    limit=10,
    output_fields=["id"]
)

for i, hits in enumerate(results):
    print(f"\nQuery {i}:")
    for hit in hits:
        print(f"id={hit.id}, dist={hit.distance}")
