from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
import faiss
import numpy as np

# 示例文档集
docs = [
    "Apple makes iPhones and MacBooks.",
    "Microsoft develops Windows and Surface laptops.",
    "Google builds Android phones and services.",
    "Apple is a major laptop brand.",
    "Laptops are useful for remote work.",
    "MacBook Air is a popular laptop from Apple.",
]
doc_ids = [f"D{i+1}" for i in range(len(docs))]

# Step 1: 用 BERT 编码文档
model = SentenceTransformer('all-MiniLM-L6-v2')
doc_embeddings = model.encode(docs, convert_to_numpy=True)

# Step 2: 用 Faiss 建立向量索引
index = faiss.IndexFlatL2(doc_embeddings.shape[1])
index.add(doc_embeddings)

# Step 3: 编码查询并 Faiss 检索
query = "best apple laptop"
query_vec = model.encode([query])
top_k = 5
D, I = index.search(query_vec, top_k)

bert_results = [doc_ids[i] for i in I[0]]

# Step 4: 用 BM25 检索
tokenized_corpus = [doc.lower().split() for doc in docs]
bm25 = BM25Okapi(tokenized_corpus)
bm25_scores = bm25.get_scores(query.lower().split())
bm25_ranked_ids = [doc_ids[i] for i in np.argsort(bm25_scores)[::-1][:top_k]]

# Step 5: RRF 融合
from collections import defaultdict

def reciprocal_rank_fusion(rankings, k=60):
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

fused = reciprocal_rank_fusion([bm25_ranked_ids, bert_results])

# 打印结果
print("Final RRF Results:")
for i, (doc_id, score) in enumerate(fused, 1):
    print(f"{i}. {doc_id}: {score:.4f} ➜ {docs[doc_ids.index(doc_id)]}")
