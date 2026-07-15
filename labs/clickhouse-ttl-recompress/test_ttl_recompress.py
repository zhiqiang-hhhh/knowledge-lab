import argparse
import unittest

from ttl_recompress import (
    Table,
    active_materialize_ttl_mutations,
    extract_ttl,
    fetch_tables,
    parse_args,
    render_alters,
    skip_reason,
    ttl_base_expression,
)


class TtlRecompressTest(unittest.TestCase):
    def test_extracts_and_preserves_existing_ttl(self):
        query = """CREATE TABLE db.t (`ts` DateTime) ENGINE = MergeTree ORDER BY ts
            TTL ts + INTERVAL 30 DAY DELETE SETTINGS index_granularity = 8192"""
        self.assertEqual(extract_ttl(query), "ts + INTERVAL 30 DAY DELETE")

    def test_does_not_treat_column_ttl_as_table_ttl(self):
        query = "CREATE TABLE db.t (`ts` DateTime, `x` UInt8 TTL ts + INTERVAL 1 DAY) ENGINE = MergeTree ORDER BY ts"
        self.assertIsNone(extract_ttl(query))

    def test_renders_setting_before_complete_ttl(self):
        table = Table("db", "t", "", "toStartOfWeek(ts)", 100, 1024)
        statements = render_alters(table, "ts + INTERVAL 30 DAY DELETE", table.partition_key, "ZSTD", "prod")
        self.assertIn("MODIFY SETTING materialize_ttl_recalculate_only = true", statements[0])
        self.assertIn("merge_with_recompression_ttl_timeout = 1800", statements[0])
        self.assertIn(
            "TTL ts + INTERVAL 30 DAY DELETE, toStartOfWeek(ts) + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD)",
            statements[1],
        )
        self.assertIn("ON CLUSTER `prod`", statements[1])

    def test_accepts_tomonday_partition_key_with_interval_offset(self):
        partition_key = "toMonday(time + toIntervalDay(1))"
        self.assertEqual(ttl_base_expression(partition_key, {"time": "DateTime"}), partition_key)

    def test_skips_tables_with_existing_ttl_move(self):
        table = Table("db", "t", "", "toMonday(time + toIntervalDay(1))", 100, 1024)
        ttl = "time TO VOLUME 'default', time + toIntervalDay(3) TO VOLUME 's3_disk'"
        self.assertEqual(skip_reason(table, ttl, table.partition_key), "already has TTL MOVE")

    def test_recompress_expression_argument_is_removed(self):
        with self.assertRaises(SystemExit):
            parse_args(["--recompress-expression", "ts + INTERVAL 1 DAY"])

    def test_fetches_only_largest_active_tables(self):
        class Result:
            def __init__(self, rows):
                self.result_rows = rows

        class Client:
            queries = []

            def query(self, query):
                self.queries.append(query)
                if "FROM system.parts" in query:
                    return Result([("db", "t", 7, 42)])
                return Result([("db", "t", "CREATE TABLE db.t (ts DateTime) ENGINE=MergeTree ORDER BY ts", "ts")])

        client = Client()
        args = argparse.Namespace(databases=None, tables=None, limit=20, all=False, metadata_batch_size=50)
        tables = fetch_tables(client, args)
        self.assertIn("FROM system.parts", client.queries[0])
        self.assertIn("WHERE active", client.queries[0])
        self.assertIn("ORDER BY total_bytes DESC", client.queries[0])
        self.assertIn("LIMIT 20", client.queries[0])
        self.assertEqual((tables[0].total_rows, tables[0].total_bytes), (7, 42))

    def test_counts_global_active_materialize_ttl_mutations(self):
        class Result:
            result_rows = [(11,)]

        class Client:
            query_text = ""

            def query(self, query):
                self.query_text = query
                return Result()

        client = Client()
        self.assertEqual(active_materialize_ttl_mutations(client), 11)
        self.assertIn("FROM system.mutations", client.query_text)
        self.assertIn("is_done = 0", client.query_text)
        self.assertIn("MATERIALIZE TTL", client.query_text)
        self.assertNotIn("database =", client.query_text)
        self.assertNotIn("table =", client.query_text)


if __name__ == "__main__":
    unittest.main()
