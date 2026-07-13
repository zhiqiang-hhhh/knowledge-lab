#!/usr/bin/env python3
"""Plan or apply a TTL RECOMPRESS rule to ClickHouse MergeTree tables."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass

try:
    import clickhouse_connect
except ModuleNotFoundError:  # Allow --help without the optional dependency.
    clickhouse_connect = None


SYSTEM_DATABASES = {"system", "INFORMATION_SCHEMA", "information_schema"}


@dataclass(frozen=True)
class Table:
    database: str
    name: str
    create_query: str
    partition_key: str
    total_rows: int
    total_bytes: int


def quote_ident(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def quote_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def qualified(table: Table) -> str:
    return f"{quote_ident(table.database)}.{quote_ident(table.name)}"


def scan_top_level(sql: str):
    depth = 0
    quote = ""
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 2
                    continue
                quote = ""
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        yield index, depth, quote
        index += 1


def find_keyword(sql: str, keyword: str, start: int = 0) -> int:
    lower = sql.lower()
    target = keyword.lower()
    for index, depth, quote in scan_top_level(sql):
        if index < start or depth or quote or not lower.startswith(target, index):
            continue
        before = sql[index - 1] if index else " "
        end = index + len(target)
        after = sql[end] if end < len(sql) else " "
        if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
            return index
    return -1


def extract_ttl(create_query: str) -> str | None:
    """Extract the table-level TTL clause, excluding column TTL declarations."""
    ttl = find_keyword(create_query, "TTL")
    if ttl < 0:
        return None
    start = ttl + len("TTL")
    ends = [
        position
        for keyword in ("SETTINGS", "COMMENT", "AS", "EMPTY")
        if (position := find_keyword(create_query, keyword, start)) >= 0
    ]
    value = create_query[start : min(ends, default=len(create_query))].strip()
    return value or None


def has_recompress(ttl: str) -> bool:
    return re.search(r"\bRECOMPRESS\b", ttl, re.IGNORECASE) is not None


def render_alters(table: Table, ttl: str | None, codec: str, cluster: str | None) -> list[str]:
    on_cluster = f" ON CLUSTER {quote_ident(cluster)}" if cluster else ""
    new_rule = f"{table.partition_key} + INTERVAL 1 WEEK RECOMPRESS CODEC({codec})"
    full_ttl = f"{ttl}, {new_rule}" if ttl else new_rule
    return [
        f"ALTER TABLE {qualified(table)}{on_cluster} MODIFY SETTING materialize_ttl_recalculate_only = true",
        f"ALTER TABLE {qualified(table)}{on_cluster} MODIFY TTL {full_ttl}",
    ]


def csv_values(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def fetch_tables(client, args: argparse.Namespace) -> list[Table]:
    conditions = ["active"]
    databases = csv_values(args.databases)
    if databases:
        conditions.append("database IN (" + ", ".join(map(quote_literal, databases)) + ")")
    else:
        conditions.append("database NOT IN (" + ", ".join(map(quote_literal, sorted(SYSTEM_DATABASES))) + ")")
    tables = csv_values(args.tables)
    if tables:
        conditions.append("`table` IN (" + ", ".join(map(quote_literal, tables)) + ")")
    result = client.query(
        """
        SELECT
            metadata.database,
            metadata.name,
            metadata.create_table_query,
            metadata.partition_key,
            ranked.total_rows,
            ranked.total_bytes
        FROM
        (
            SELECT
                database,
                `table`,
                sum(rows) AS total_rows,
                sum(bytes) AS total_bytes
            FROM system.parts
            WHERE """
        + " AND ".join(conditions)
        + f"""
            GROUP BY database, `table`
            ORDER BY total_bytes DESC
            LIMIT {args.limit}
        ) AS ranked
        INNER JOIN system.tables AS metadata
            ON ranked.database = metadata.database AND ranked.`table` = metadata.name
        WHERE metadata.engine LIKE '%MergeTree%'
        ORDER BY ranked.total_bytes DESC, metadata.database, metadata.name
        """
    )
    return [
        Table(str(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]), int(row[5]))
        for row in result.result_rows
    ]


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def skip_reason(table: Table, ttl: str | None) -> str | None:
    if not table.partition_key.strip():
        return "empty partition key"
    if ttl and has_recompress(ttl):
        return "already has TTL RECOMPRESS"
    return None


def print_table_plan(index: int, table: Table, ttl: str | None, statements: list[str] | None, reason: str | None) -> None:
    print(f"-- [{index}] {table.database}.{table.name}")
    print(f"-- rows: {table.total_rows}")
    print(f"-- bytes: {table.total_bytes} ({format_bytes(table.total_bytes)})")
    print(f"-- current partition key: {table.partition_key or '(none)'}")
    print(f"-- current table TTL: {ttl or '(none)'}")
    if reason:
        print(f"-- skip reason: {reason}")
    else:
        assert statements is not None
        print(f"-- planned setting: {statements[0]}")
        print(f"-- planned TTL: {statements[1]}")
    print()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8123, help="ClickHouse HTTP(S) port")
    parser.add_argument("--user", default="default")
    parser.add_argument("--password", default="")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--databases", help="Comma-separated database allowlist")
    parser.add_argument("--tables", help="Comma-separated unqualified table-name allowlist")
    parser.add_argument("--cluster", help="Add ON CLUSTER to both ALTER statements")
    parser.add_argument("--codec", default="ZSTD", help="Codec expression inside CODEC(...); default: ZSTD")
    parser.add_argument("--limit", type=int, default=20, help="Maximum largest active tables to process; default: 20")
    parser.add_argument("--apply", action="store_true", help="Execute the plan; default is dry-run")
    args = parser.parse_args(argv)
    if ";" in args.codec:
        parser.error("codec must not contain semicolons")
    if not args.codec.strip():
        parser.error("codec must not be empty")
    if args.limit <= 0:
        parser.error("limit must be positive")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if clickhouse_connect is None:
        print("missing dependency: pip install clickhouse-connect", file=sys.stderr)
        return 2
    client = clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        secure=args.secure,
    )
    tables = fetch_tables(client, args)
    print(f"Top {args.limit} active tables by bytes (selected={len(tables)}):")
    for index, table in enumerate(tables, start=1):
        print(
            f"  {index}. {table.database}.{table.name} "
            f"rows={table.total_rows} bytes={table.total_bytes} ({format_bytes(table.total_bytes)})"
        )
    print()

    planned = skipped = 0
    for index, table in enumerate(tables, start=1):
        ttl = extract_ttl(table.create_query)
        reason = skip_reason(table, ttl)
        if reason:
            print_table_plan(index, table, ttl, None, reason)
            skipped += 1
            continue
        statements = render_alters(table, ttl, args.codec.strip(), args.cluster)
        print_table_plan(index, table, ttl, statements, None)
        for statement in statements:
            if args.apply:
                client.command(statement)
        planned += 1
    print(f"mode={'apply' if args.apply else 'dry-run'} planned={planned} skipped={skipped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
