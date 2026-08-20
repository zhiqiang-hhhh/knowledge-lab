import argparse
import io
import unittest
from contextlib import redirect_stdout

import os
import tempfile

from ttl_recompress import (
    ClusterNode,
    PlannedTable,
    StorageTopology,
    Table,
    active_materialize_ttl_mutations,
    load_clusters_dir,
    merge_tables,
    merge_topologies,
    parse_cluster_file,
    parse_cluster_node,
    apply_repair_settings,
    apply_table,
    extract_column_types,
    extract_ttl,
    fetch_repair_setting_tables,
    fetch_tables,
    materialize_ttl_recalculate_only_enabled,
    plan_tables,
    plan_repair_settings,
    parse_args,
    print_analysis,
    print_repair_setting_analysis,
    print_skipped_table_summary,
    render_alters,
    render_repair_setting_alter,
    skip_reason,
    summarize_planned_tables,
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
        statements = render_alters(table, "ts + INTERVAL 30 DAY DELETE", table.partition_key, "ZSTD", "prod", False)
        self.assertIn("MODIFY SETTING materialize_ttl_recalculate_only = true", statements[0])
        self.assertNotIn("merge_with_recompression_ttl_timeout", statements[0])
        self.assertNotIn("materialize_ttl_after_modify", statements[0])
        self.assertIn(
            "TTL ts + INTERVAL 30 DAY DELETE, toStartOfWeek(ts) + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD)",
            statements[1],
        )
        self.assertIn("SETTINGS materialize_ttl_after_modify = 0", statements[1])
        self.assertIn("ON CLUSTER `prod`", statements[1])

    def test_default_disables_materialize_ttl_after_modify(self):
        table = Table("db", "t", "", "ts", 100, 1024)
        statements = render_alters(table, None, table.partition_key, "ZSTD", None, False)
        self.assertNotIn("materialize_ttl_after_modify", statements[0])
        self.assertIn("MODIFY TTL ts + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD)", statements[1])
        self.assertIn("SETTINGS materialize_ttl_after_modify = 0", statements[1])

    def test_can_enable_materialize_ttl_after_modify(self):
        table = Table("db", "t", "", "ts", 100, 1024)
        statements = render_alters(table, None, table.partition_key, "ZSTD", None, True)
        self.assertNotIn("materialize_ttl_after_modify", statements[0])
        self.assertIn("MODIFY TTL ts + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD)", statements[1])
        self.assertNotIn("SETTINGS materialize_ttl_after_modify = 0", statements[1])

    def test_skips_setting_alter_when_required_settings_exist(self):
        create_query = """CREATE TABLE db.t (`ts` DateTime) ENGINE = MergeTree ORDER BY ts
            SETTINGS materialize_ttl_recalculate_only = 1,
                     index_granularity = 8192"""
        table = Table("db", "t", create_query, "ts", 100, 1024)
        statements = render_alters(table, None, table.partition_key, "ZSTD", None, False)
        self.assertEqual(len(statements), 1)
        self.assertIn("MODIFY TTL ts + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD)", statements[0])
        self.assertIn("SETTINGS materialize_ttl_after_modify = 0", statements[0])
        self.assertNotIn("MODIFY SETTING materialize_ttl_recalculate_only", statements[0])

    def test_apply_skips_satisfied_setting_alter(self):
        class Result:
            result_rows = [(0,)]

        class Client:
            commands = []

            def query(self, query):
                return Result()

            def command(self, query):
                self.commands.append(query)

        client = Client()
        table = Table("db", "t", "", "ts", 100, 1024)
        apply_table(
            client,
            1,
            1,
            table,
            ["ALTER TABLE `db`.`t` MODIFY TTL ts + INTERVAL 1 WEEK RECOMPRESS CODEC(ZSTD)"],
            False,
        )
        self.assertEqual(len(client.commands), 1)
        self.assertIn("MODIFY TTL", client.commands[0])

    def test_repair_setting_detects_missing_or_disabled_setting(self):
        tables = [
            Table(
                "db",
                "missing",
                "CREATE TABLE db.missing (ts DateTime) ENGINE=MergeTree ORDER BY ts "
                "TTL ts + INTERVAL 1 DAY RECOMPRESS CODEC(ZSTD)",
                "ts",
                0,
                0,
            ),
            Table(
                "db",
                "disabled",
                "CREATE TABLE db.disabled (ts DateTime) ENGINE=MergeTree ORDER BY ts "
                "TTL ts + INTERVAL 1 DAY RECOMPRESS CODEC(ZSTD) "
                "SETTINGS materialize_ttl_recalculate_only = 0",
                "ts",
                0,
                0,
            ),
            Table(
                "db",
                "enabled",
                "CREATE TABLE db.enabled (ts DateTime) ENGINE=MergeTree ORDER BY ts "
                "TTL ts + INTERVAL 1 DAY RECOMPRESS CODEC(ZSTD) "
                "SETTINGS MATERIALIZE_TTL_RECALCULATE_ONLY = TRUE",
                "ts",
                0,
                0,
            ),
            Table(
                "db",
                "delete_only",
                "CREATE TABLE db.delete_only (ts DateTime) ENGINE=MergeTree ORDER BY ts "
                "TTL ts + INTERVAL 30 DAY DELETE",
                "ts",
                0,
                0,
            ),
        ]
        plan = plan_repair_settings(tables)
        self.assertEqual([table.name for table in plan.recompress_tables], ["missing", "disabled", "enabled"])
        self.assertEqual([table.name for table in plan.repair_tables], ["missing", "disabled"])
        self.assertTrue(materialize_ttl_recalculate_only_enabled(tables[2].create_query))

    def test_repair_setting_ignores_column_ttl_recompress(self):
        table = Table(
            "db",
            "column_ttl",
            "CREATE TABLE db.column_ttl (ts DateTime, value String TTL ts + INTERVAL 1 DAY "
            "RECOMPRESS CODEC(ZSTD)) ENGINE=MergeTree ORDER BY ts",
            "ts",
            0,
            0,
        )
        self.assertEqual(plan_repair_settings([table]).recompress_tables, [])

    def test_renders_repair_setting_with_cluster(self):
        table = Table("db", "t", "", "ts", 0, 0)
        self.assertEqual(
            render_repair_setting_alter(table, "prod"),
            "ALTER TABLE `db`.`t` ON CLUSTER `prod` MODIFY SETTING "
            "materialize_ttl_recalculate_only = true",
        )

    def test_prints_repair_setting_counts_and_sql(self):
        missing = Table(
            "db",
            "missing",
            "CREATE TABLE db.missing (ts DateTime) ENGINE=MergeTree ORDER BY ts "
            "TTL ts RECOMPRESS CODEC(ZSTD)",
            "ts",
            0,
            0,
        )
        enabled = Table(
            "db",
            "enabled",
            "CREATE TABLE db.enabled (ts DateTime) ENGINE=MergeTree ORDER BY ts "
            "TTL ts RECOMPRESS CODEC(ZSTD) SETTINGS materialize_ttl_recalculate_only = 1",
            "ts",
            0,
            0,
        )
        output = io.StringIO()
        with redirect_stdout(output):
            print_repair_setting_analysis(plan_repair_settings([missing, enabled]), None)
        value = output.getvalue()
        self.assertIn("tables with TTL RECOMPRESS: 2", value)
        self.assertIn("repair needed: 1", value)
        self.assertIn("already enabled: 1", value)
        self.assertIn("ALTER TABLE `db`.`missing`", value)
        self.assertNotIn("ALTER TABLE `db`.`enabled`", value)

    def test_fetch_repair_setting_scans_system_tables_without_parts_or_limit(self):
        class Result:
            def __init__(self, result_rows):
                self.result_rows = result_rows

        class Client:
            queries = []

            def query(self, query):
                self.queries.append(query)
                if "create_table_query" in query:
                    return Result([("db", "empty", "CREATE TABLE db.empty (ts DateTime) ENGINE=MergeTree ORDER BY ts", "ts")])
                return Result([("db", "empty")])

        client = Client()
        args = argparse.Namespace(databases=None, tables=None, metadata_batch_size=50)
        tables = fetch_repair_setting_tables(client, args)
        self.assertEqual(tables[0].name, "empty")
        self.assertIn("FROM system.tables", client.queries[0])
        self.assertNotIn("create_table_query", client.queries[0])
        self.assertNotIn("system.parts", "\n".join(client.queries))
        self.assertNotIn("LIMIT", "\n".join(client.queries))
        self.assertIn("database NOT IN", client.queries[0])
        self.assertIn("create_table_query", client.queries[1])

    def test_apply_repair_only_runs_setting_alters(self):
        class Client:
            def __init__(self):
                self.commands = []

            def command(self, query):
                self.commands.append(query)

        client = Client()
        args = argparse.Namespace(apply_concurrency=1, cluster=None)
        apply_repair_settings(client, args, [Table("db", "t", "", "ts", 0, 0)])
        self.assertEqual(len(client.commands), 1)
        self.assertIn("MODIFY SETTING materialize_ttl_recalculate_only = true", client.commands[0])
        self.assertNotIn("MODIFY TTL", client.commands[0])

    def test_apply_repair_is_mutually_exclusive_with_normal_apply(self):
        with self.assertRaises(SystemExit):
            parse_args(["--apply", "--apply-repair"])

    def test_accepts_tomonday_partition_key_with_interval_offset(self):
        partition_key = "toMonday(time + toIntervalDay(1))"
        self.assertEqual(ttl_base_expression(partition_key, {"time": "DateTime"}), partition_key)

    def test_converts_datetime64_partition_key_to_datetime_for_ttl(self):
        self.assertEqual(ttl_base_expression("event_time", {"event_time": "DateTime64(3)"}), "toDateTime(event_time)")

    def test_converts_datetime64_partition_key_argument_to_datetime_for_ttl(self):
        self.assertEqual(
            ttl_base_expression("toYYYYMM(event_time)", {"event_time": "DateTime64(3)"}),
            "toDateTime(event_time)",
        )

    def test_converts_datetime64_tomonday_partition_key_to_datetime_for_ttl(self):
        partition_key = "toMonday(time + toIntervalDay(1))"
        self.assertEqual(
            ttl_base_expression(partition_key, {"time": "DateTime64(3)"}),
            f"toDateTime({partition_key})",
        )

    def test_converts_datetime64_tostartofinterval_partition_key_to_datetime_for_ttl(self):
        partition_key = "toStartOfInterval(event_time, INTERVAL 1 minute)"
        self.assertEqual(
            ttl_base_expression(partition_key, {"event_time": "DateTime64(3)"}),
            f"toDateTime({partition_key})",
        )

    def test_converts_todatetime64_partition_key_to_datetime_for_ttl(self):
        partition_key = "toDateTime64(event_time_ms / 1000, 3)"
        self.assertEqual(ttl_base_expression(partition_key, {}), f"toDateTime({partition_key})")

    def test_extracts_column_types_from_single_line_create_query(self):
        # ClickHouse system.tables.create_table_query returns a single-line
        # form with columns separated by top-level commas, not newlines.
        create_query = (
            "CREATE TABLE db.t (`id` String, `accountId` String, "
            "`createTime` DateTime64(3), `modifyTime` DateTime64(3)) "
            "ENGINE = MergeTree ORDER BY id"
        )
        self.assertEqual(
            extract_column_types(create_query),
            {
                "id": "String",
                "accountId": "String",
                "createTime": "DateTime64(3)",
                "modifyTime": "DateTime64(3)",
            },
        )

    def test_extracts_column_types_skips_inline_index_definitions(self):
        create_query = (
            "CREATE TABLE db.t (`id` String, `createTime` DateTime64(3), "
            "INDEX idx_id engagementId TYPE ngrambf_v1(3, 256, 2, 0) GRANULARITY 4, "
            "INDEX idx_bloom engagementId TYPE bloom_filter GRANULARITY 4) "
            "ENGINE = MergeTree ORDER BY id"
        )
        column_types = extract_column_types(create_query)
        self.assertEqual(column_types.get("createTime"), "DateTime64(3)")
        self.assertNotIn("INDEX", column_types)

    def test_single_line_create_query_yields_wrapped_datetime64_ttl_base(self):
        create_query = (
            "CREATE TABLE db.t (`id` String, `createTime` DateTime64(3)) "
            "ENGINE = MergeTree PARTITION BY toYYYYMM(createTime) ORDER BY id "
            "TTL toDateTime(createTime) + toIntervalDay(180)"
        )
        column_types = extract_column_types(create_query)
        self.assertEqual(
            ttl_base_expression("toYYYYMM(createTime)", column_types),
            "toDateTime(createTime)",
        )

    def test_skips_tables_without_table_ttl_delete(self):
        table = Table("db", "t", "", "toYYYYMM(time)", 100, 1024)
        self.assertEqual(skip_reason(table, None, "toDateTime(time)"), "no table TTL DELETE")

    def test_accepts_implicit_table_ttl_delete(self):
        table = Table("db", "t", "", "toYYYYMM(time)", 100, 1024)
        self.assertIsNone(skip_reason(table, "time + INTERVAL 30 DAY", "toDateTime(time)"))

    def test_accepts_tables_with_existing_ttl_move_by_default(self):
        table = Table("db", "t", "", "toMonday(time + toIntervalDay(1))", 100, 1024)
        ttl = "time TO VOLUME 'default', time + toIntervalDay(30)"
        self.assertIsNone(skip_reason(table, ttl, table.partition_key))
        planned = plan_tables(
            [
                Table(
                    "db",
                    "t",
                    "CREATE TABLE db.t (`time` DateTime) ENGINE = MergeTree PARTITION BY toMonday(time) "
                    "ORDER BY time TTL time TO VOLUME 'default', time + INTERVAL 30 DAY",
                    "toMonday(time)",
                    100,
                    1024,
                )
            ]
        )
        self.assertIsNone(planned[0].reason)

    def test_ttl_move_recompresses_after_one_day(self):
        table = Table("db", "t", "", "toMonday(time)", 100, 1024)
        ttl = "time + INTERVAL 3 DAY TO VOLUME 's3_disk', time + INTERVAL 30 DAY"
        statements = render_alters(table, ttl, table.partition_key, "ZSTD", None, False)
        self.assertIn(
            "TTL time + INTERVAL 3 DAY TO VOLUME 's3_disk', time + INTERVAL 30 DAY, "
            "toMonday(time) + INTERVAL 1 DAY RECOMPRESS CODEC(ZSTD)",
            statements[-1],
        )
        self.assertNotIn("INTERVAL 1 WEEK RECOMPRESS", statements[-1])

    def test_skips_move_only_ttl(self):
        table = Table("db", "t", "", "toMonday(time + toIntervalDay(1))", 100, 1024)
        ttl = "time TO VOLUME 'default', time + toIntervalDay(3) TO VOLUME 's3_disk'"
        self.assertEqual(skip_reason(table, ttl, table.partition_key), "no table TTL DELETE")

    def test_mixed_move_and_local_tables_choose_materialize_per_table(self):
        table = Table("db", "t", "", "toMonday(time)", 100, 1024)
        move_ttl = "time + INTERVAL 3 DAY TO VOLUME 's3_disk', time + INTERVAL 30 DAY"
        local_ttl = "time + INTERVAL 30 DAY"

        move_statements = render_alters(table, move_ttl, table.partition_key, "ZSTD", None, True)
        local_statements = render_alters(table, local_ttl, table.partition_key, "ZSTD", None, True)

        self.assertIn("materialize_ttl_recalculate_only = true", move_statements[0])
        self.assertIn("materialize_ttl_recalculate_only = true", local_statements[0])
        self.assertIn("SETTINGS materialize_ttl_after_modify = 0", move_statements[-1])
        self.assertNotIn("materialize_ttl_after_modify", local_statements[-1])

    def test_skips_system_database_tables(self):
        table = Table("system", "query_log", "", "event_date", 100, 1024)
        self.assertEqual(skip_reason(table, None, table.partition_key), "system database")

    def test_ttl_move_default_does_not_include_system_database_tables(self):
        table = Table("system", "query_log", "", "event_date", 100, 1024)
        self.assertEqual(skip_reason(table, None, table.partition_key), "system database")

    def test_recompress_expression_argument_is_removed(self):
        with self.assertRaises(SystemExit):
            parse_args(["--recompress-expression", "ts + INTERVAL 1 DAY"])

    def test_analysis_and_apply_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            parse_args(["--analysis", "--apply"])

    def test_summarizes_analysis_totals(self):
        planned_tables = [
            PlannedTable(Table("db", "eligible", "", "ts", 10, 1000, 800, 200), None, "ts", None),
            PlannedTable(Table("db", "skipped", "", "", 5, 250), None, None, "empty partition key"),
        ]
        self.assertEqual(
            summarize_planned_tables(planned_tables),
            {
                "selected_tables": 2,
                "eligible_tables": 1,
                "skipped_tables": 1,
                "selected_rows": 15,
                "eligible_rows": 10,
                "skipped_rows": 5,
                "selected_bytes": 1250,
                "eligible_bytes": 1000,
                "skipped_bytes": 250,
                "eligible_local_bytes": 800,
                "eligible_remote_bytes": 200,
            },
        )

    def test_prints_analysis_skip_reasons(self):
        planned_tables = [
            PlannedTable(Table("db", "eligible", "", "ts", 10, 1000, 1000, 0), None, "ts", None),
            PlannedTable(Table("db", "skipped", "", "", 5, 250), None, None, "empty partition key"),
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            print_analysis(planned_tables)
        value = output.getvalue()
        self.assertIn("Analysis summary:", value)
        self.assertIn("eligible: tables=1 rows=10 bytes=1000", value)
        self.assertIn("empty partition key: tables=1 bytes=250", value)
        self.assertIn("local-only: tables=1 local_bytes=1000", value)
        self.assertIn("total eligible local disk bytes: 1000", value)
        self.assertIn("Top eligible local-only tables by bytes", value)
        self.assertIn("Top skipped tables by bytes", value)

    def test_analysis_separates_local_local_move_and_s3_move_tables(self):
        planned_tables = [
            PlannedTable(
                Table("db", "local", "", "ts", 10, 1000, 1000, 0),
                "ts + INTERVAL 30 DAY DELETE",
                "ts",
                None,
            ),
            PlannedTable(
                Table("db", "local_move", "", "ts", 15, 1200, 1200, 0, "s3_policy"),
                "ts TO VOLUME 'default', ts + INTERVAL 30 DAY DELETE",
                "ts",
                None,
            ),
            PlannedTable(
                Table("db", "tiered", "", "ts", 20, 2000, 500, 1500, "s3_policy"),
                "ts + INTERVAL 3 DAY TO VOLUME 's3_disk', ts + INTERVAL 30 DAY DELETE",
                "ts",
                None,
            ),
        ]
        topology = StorageTopology(
            frozenset({"s3_disk"}),
            {
                ("s3_policy", "default"): ("default",),
                ("s3_policy", "s3_disk"): ("s3_disk",),
            },
        )
        output = io.StringIO()
        with redirect_stdout(output):
            print_analysis(planned_tables, topology=topology)
        value = output.getvalue()
        self.assertIn("local-only: tables=1 local_bytes=1000", value)
        self.assertIn("local-volume-move: tables=1 local_bytes=1200", value)
        self.assertIn("S3/remote-move: tables=1 local_bytes=500", value)
        self.assertIn("remote_bytes=1500", value)
        self.assertIn("total eligible local disk bytes: 2700", value)
        self.assertIn("db.local", value)
        self.assertIn("db.local_move", value)
        self.assertIn("db.tiered", value)

    def test_prints_skipped_summary_with_reasons(self):
        planned_tables = [
            PlannedTable(Table("db", "eligible", "", "ts", 10, 1000), None, "ts", None),
            PlannedTable(Table("db", "skipped", "", "", 5, 250), None, None, "empty partition key"),
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            print_skipped_table_summary(planned_tables)
        value = output.getvalue()
        self.assertIn("Top skipped tables by bytes", value)
        self.assertIn("db.skipped", value)
        self.assertIn("reason=empty partition key", value)

    def test_analysis_can_print_expanded_skipped_summary(self):
        planned_tables = [
            PlannedTable(Table("db", "eligible", "", "ts", 10, 1000), None, "ts", None),
            PlannedTable(Table("db", "skipped1", "", "", 5, 250), None, None, "empty partition key"),
        ]
        skipped_summary_plan = planned_tables + [
            PlannedTable(
                Table("db", "skipped2", "", "tuple(ts, tenant)", 7, 125),
                None,
                None,
                "unsupported partition key for TTL base expression",
            ),
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            print_analysis(planned_tables, skipped_summary_plan, limit=2)
        value = output.getvalue()
        self.assertIn("selected: tables=2 rows=15 bytes=1250", value)
        self.assertIn("db.skipped1", value)
        self.assertIn("db.skipped2", value)

    def test_fetches_only_largest_active_tables(self):
        class Result:
            def __init__(self, rows):
                self.result_rows = rows

        class Client:
            queries = []

            def query(self, query):
                self.queries.append(query)
                if "FROM system.parts" in query:
                    return Result([("db", "t", 7, 42, 30, 12)])
                return Result([("db", "t", "CREATE TABLE db.t (ts DateTime) ENGINE=MergeTree ORDER BY ts", "ts")])

        client = Client()
        args = argparse.Namespace(databases=None, tables=None, limit=20, all=False, metadata_batch_size=50)
        tables = fetch_tables(client, args)
        self.assertIn("FROM system.parts", client.queries[0])
        self.assertIn("LEFT JOIN system.disks", client.queries[0])
        self.assertIn("d.is_remote", client.queries[0])
        self.assertIn("WHERE p.active", client.queries[0])
        self.assertIn("ORDER BY total_bytes DESC", client.queries[0])
        self.assertIn("LIMIT 20", client.queries[0])
        self.assertEqual((tables[0].total_rows, tables[0].total_bytes), (7, 42))
        self.assertEqual((tables[0].local_bytes, tables[0].remote_bytes), (30, 12))

    def test_analysis_fetch_can_include_system_tables_without_limit(self):
        class Result:
            def __init__(self, rows):
                self.result_rows = rows

        class Client:
            queries = []

            def query(self, query):
                self.queries.append(query)
                if "FROM system.parts" in query:
                    return Result([("system", "query_log", 7, 42)])
                return Result(
                    [
                        (
                            "system",
                            "query_log",
                            "CREATE TABLE system.query_log (event_date Date) ENGINE=MergeTree ORDER BY event_date",
                            "event_date",
                        )
                    ]
                )

        client = Client()
        args = argparse.Namespace(
            databases=None,
            tables=None,
            limit=20,
            all=True,
            metadata_batch_size=50,
            include_system=True,
        )
        tables = fetch_tables(client, args)
        self.assertIn("FROM system.parts", client.queries[0])
        self.assertNotIn("database NOT IN", client.queries[0])
        self.assertNotIn("LIMIT 20", client.queries[0])
        self.assertIn("FROM system.tables", client.queries[1])
        self.assertNotIn("database NOT IN", client.queries[1])
        self.assertEqual(tables[0].database, "system")
        self.assertEqual(plan_tables(tables)[0].reason, "system database")

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


class ClustersFileTest(unittest.TestCase):
    def test_parse_cluster_node_variants(self):
        self.assertEqual(parse_cluster_node("10.0.0.1", 8123), ClusterNode("10.0.0.1", 8123))
        self.assertEqual(parse_cluster_node("10.0.0.1:9000", 8123), ClusterNode("10.0.0.1", 9000))
        self.assertEqual(parse_cluster_node("[::1]:9440", 8123), ClusterNode("::1", 9440))
        self.assertEqual(parse_cluster_node("[fe80::1]", 8123), ClusterNode("fe80::1", 8123))
        self.assertEqual(parse_cluster_node("host.example.com", None), ClusterNode("host.example.com", None))

    def test_parse_cluster_file(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "perf-CH1-arm.txt")
        with open(path, "w") as handle:
            handle.write("# arm cluster\n10.21.5.164\n10.21.5.44:9000  # primary\n\n")
        try:
            cluster = parse_cluster_file(path, default_port=8123)
        finally:
            os.unlink(path)
            os.rmdir(directory)
        self.assertEqual(cluster.name, "perf-CH1-arm")
        self.assertEqual(
            cluster.nodes,
            (ClusterNode("10.21.5.164", 8123), ClusterNode("10.21.5.44", 9000)),
        )

    def test_load_clusters_dir(self):
        directory = tempfile.mkdtemp()
        with open(os.path.join(directory, "clusterB.txt"), "w") as handle:
            handle.write("10.0.1.1\n")
        with open(os.path.join(directory, "clusterA.txt"), "w") as handle:
            handle.write("10.0.0.1\n10.0.0.2\n")
        with open(os.path.join(directory, "empty.txt"), "w") as handle:
            handle.write("# only a comment\n")
        with open(os.path.join(directory, "ignored.md"), "w") as handle:
            handle.write("10.9.9.9\n")
        try:
            clusters = load_clusters_dir(directory, default_port=8123)
        finally:
            for name in os.listdir(directory):
                os.unlink(os.path.join(directory, name))
            os.rmdir(directory)
        self.assertEqual([c.name for c in clusters], ["clusterA", "clusterB"])  # sorted, empty/.md dropped
        self.assertEqual(
            clusters[0].nodes,
            (ClusterNode("10.0.0.1", 8123), ClusterNode("10.0.0.2", 8123)),
        )

    def test_load_clusters_dir_requires_a_cluster(self):
        directory = tempfile.mkdtemp()
        try:
            with self.assertRaises(ValueError):
                load_clusters_dir(directory)
        finally:
            os.rmdir(directory)


class MergeTablesTest(unittest.TestCase):
    def _table(self, name, rows, total, local, remote):
        return Table("db", name, "CREATE TABLE db." + name, "toDate(ts)", rows, total, local, remote, "policy")

    def test_merge_sums_and_sorts(self):
        node1 = [self._table("a", 10, 100, 60, 40), self._table("b", 5, 50, 50, 0)]
        node2 = [self._table("a", 20, 200, 100, 100)]
        merged = merge_tables([node1, node2])
        self.assertEqual([t.name for t in merged], ["a", "b"])  # sorted by total_bytes desc
        a = merged[0]
        self.assertEqual((a.total_rows, a.total_bytes, a.local_bytes, a.remote_bytes), (30, 300, 160, 140))

    def test_merge_topologies_unions(self):
        topo = merge_topologies([
            StorageTopology(frozenset({"s3"}), {("p", "v1"): ("d1",)}),
            StorageTopology(frozenset({"s3b"}), {("p", "v2"): ("d2",)}),
        ])
        self.assertEqual(topo.remote_disks, frozenset({"s3", "s3b"}))
        self.assertEqual(topo.volume_disks, {("p", "v1"): ("d1",), ("p", "v2"): ("d2",)})


if __name__ == "__main__":
    unittest.main()
