-- ============================================================
-- Dataset: sift_user_100w_pq
-- 100 users x 1,000,000 vectors = 100,000,000 rows
-- Source: datasets/dataset_100w/shard_000~099.tsv.gz (100 shards)
-- Mode: pq_on_disk ANN on embedding
-- metric_type = l2_distance, dim = 128, pq_m = 64, pq_nbits = 8
-- ============================================================

DROP TABLE IF EXISTS sift_user_100w_pq;

CREATE TABLE sift_user_100w_pq (
  user_id int NOT NULL COMMENT "用户ID (0-99)",
  id int NOT NULL COMMENT "用户内向量ID",
  embedding array<float> NOT NULL COMMENT "128维向量",
  INDEX idx_user_id (`user_id`) USING INVERTED
) ENGINE=OLAP
DUPLICATE KEY(user_id, id) COMMENT "100用户 x 100W向量 (pq_on_disk)"
DISTRIBUTED BY HASH(user_id) BUCKETS 1
PROPERTIES (
  "replication_num" = "1"
);
