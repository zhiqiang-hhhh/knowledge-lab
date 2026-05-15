-- ============================================================
-- Dataset: sift_user_50w
-- 100 users x 500,000 vectors = 50,000,000 rows
-- Source: datasets/dataset_50w/shard_000~049.tsv.gz (50 shards)
-- ============================================================

DROP TABLE IF EXISTS sift_user_50w;

CREATE TABLE sift_user_50w (
  user_id int NOT NULL COMMENT "用户ID (0-99)",
  id int NOT NULL COMMENT "用户内向量ID",
  embedding array<float> NOT NULL COMMENT "128维向量"
) ENGINE=OLAP
DUPLICATE KEY(user_id, id) COMMENT "100用户 x 50W向量"
DISTRIBUTED BY HASH(user_id) BUCKETS 16
PROPERTIES (
  "replication_num" = "1"
);

-- 导入方式一：从 S3/OSS 导入
-- INSERT INTO sift_user_50w
-- SELECT * FROM S3(
--   "uri" = "s3://your-bucket/dataset_50w/shard_*.tsv.gz",
--   "format" = "csv",
--   "column_separator" = "\t",
--   "compress_type" = "gz"
-- );

-- 导入方式二：Stream Load 批量导入（50个分片）
-- for i in $(seq -w 0 49); do
--   shard=$(printf "shard_%03d.tsv.gz" $i)
--   zcat datasets/dataset_50w/${shard} | \
--   curl --location-trusted -u user:password \
--     -H "column_separator:\t" \
--     -H "columns: user_id, id, embedding" \
--     -T - \
--     http://<fe_host>:<http_port>/api/<db>/sift_user_50w/_stream_load
-- done
