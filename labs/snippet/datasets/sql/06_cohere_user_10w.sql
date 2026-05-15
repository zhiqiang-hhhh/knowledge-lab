-- ============================================================
-- Dataset: cohere_user_10w
-- 100 users x 100,000 vectors = 10,000,000 rows
-- Source: datasets/dataset_768d_10w/shard_000~009.tsv.gz (10 shards)
-- Vectors: Cohere/wikipedia-22-12, 768D float32
-- ============================================================

DROP TABLE IF EXISTS cohere_user_10w;

CREATE TABLE cohere_user_10w (
  user_id int NOT NULL COMMENT "用户ID (0-99)",
  id int NOT NULL COMMENT "用户内向量ID",
  embedding array<float> NOT NULL COMMENT "768维向量 (Cohere)"
) ENGINE=OLAP
DUPLICATE KEY(user_id, id) COMMENT "100用户 x 10W向量 (768D)"
DISTRIBUTED BY HASH(user_id) BUCKETS 1
PROPERTIES (
  "replication_num" = "1"
);
