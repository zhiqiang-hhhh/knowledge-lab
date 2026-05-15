-- ============================================================
-- Dataset: sift_user_1w
-- 100 users x 10,000 vectors = 1,000,000 rows
-- Source: datasets/dataset_1w/shard_000.tsv.gz (1 shard)
-- ============================================================

DROP TABLE IF EXISTS sift_user_1w;

CREATE TABLE sift_user_1w (
  user_id int NOT NULL COMMENT "用户ID (0-99)",
  id int NOT NULL COMMENT "用户内向量ID",
  embedding array<float> NOT NULL COMMENT "128维向量"
) ENGINE=OLAP
DUPLICATE KEY(user_id, id) COMMENT "100用户 x 1W向量"
DISTRIBUTED BY HASH(user_id) BUCKETS 4
PROPERTIES (
  "replication_num" = "1"
);

-- 导入方式一：从 S3/OSS 导入（需替换为实际路径）
-- INSERT INTO sift_user_1w
-- SELECT * FROM S3(
--   "uri" = "s3://your-bucket/dataset_1w/shard_*.tsv.gz",
--   "format" = "csv",
--   "column_separator" = "\t",
--   "compress_type" = "gz"
-- );

-- 导入方式二：Stream Load（从本地导入）
-- 先解压：zcat datasets/dataset_1w/shard_000.tsv.gz > /tmp/shard_000.tsv
-- curl --location-trusted -u user:password \
--   -H "column_separator:\t" \
--   -H "columns: user_id, id, embedding" \
--   -T /tmp/shard_000.tsv \
--   http://<fe_host>:<http_port>/api/<db>/sift_user_1w/_stream_load
