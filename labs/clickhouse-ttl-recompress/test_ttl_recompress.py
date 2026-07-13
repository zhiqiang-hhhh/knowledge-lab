import argparse
import unittest

from ttl_recompress import Table, extract_ttl, fetch_tables, parse_args, render_alters


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
        statements = render_alters(table, "ts + INTERVAL 30 DAY DELETE", "ZSTD", "prod")
        self.assertIn("MODIFY SETTING materialize_ttl_recalculate_only = true", statements[0])
        self.assertIn(
            "TTL ts + INTERVAL 30 DAY DELETE, toStartOfWeek(ts) + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD)",
            statements[1],
        )
        self.assertIn("ON CLUSTER `prod`", statements[1])

    def test_recompress_expression_argument_is_removed(self):
        with self.assertRaises(SystemExit):
            parse_args(["--recompress-expression", "ts + INTERVAL 1 DAY"])

    def test_fetches_only_largest_active_tables(self):
        class Result:
            result_rows = [("db", "t", "CREATE TABLE db.t (ts DateTime) ENGINE=MergeTree ORDER BY ts", "ts", 7, 42)]

        class Client:
            query_text = ""

            def query(self, query):
                self.query_text = query
                return Result()

        client = Client()
        args = argparse.Namespace(databases=None, tables=None, limit=20)
        tables = fetch_tables(client, args)
        self.assertIn("FROM system.parts", client.query_text)
        self.assertIn("WHERE active", client.query_text)
        self.assertIn("ORDER BY total_bytes DESC", client.query_text)
        self.assertIn("LIMIT 20", client.query_text)
        self.assertEqual((tables[0].total_rows, tables[0].total_bytes), (7, 42))


if __name__ == "__main__":
    unittest.main()
