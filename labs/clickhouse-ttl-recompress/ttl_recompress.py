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
    conditions = ["engine LIKE '%MergeTree%'"]
    databases = csv_values(args.databases)
    if databases:
        conditions.append("database IN (" + ", ".join(map(quote_literal, databases)) + ")")
    else:
        conditions.append("database NOT IN (" + ", ".join(map(quote_literal, sorted(SYSTEM_DATABASES))) + ")")
    tables = csv_values(args.tables)
    if tables:
        conditions.append("name IN (" + ", ".join(map(quote_literal, tables)) + ")")
    result = client.query(
        "SELECT database, name, create_table_query, partition_key FROM system.tables WHERE "
        + " AND ".join(conditions)
        + " ORDER BY database, name"
    )
    return [Table(str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in result.result_rows]


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
    parser.add_argument("--apply", action="store_true", help="Execute the plan; default is dry-run")
    args = parser.parse_args(argv)
    if ";" in args.codec:
        parser.error("codec must not contain semicolons")
    if not args.codec.strip():
        parser.error("codec must not be empty")
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
    planned = skipped = 0
    for table in fetch_tables(client, args):
        if not table.partition_key.strip():
            print(f"SKIP {table.database}.{table.name}: empty partition key", file=sys.stderr)
            skipped += 1
            continue
        ttl = extract_ttl(table.create_query)
        if ttl and has_recompress(ttl):
            print(f"SKIP {table.database}.{table.name}: already has TTL RECOMPRESS", file=sys.stderr)
            skipped += 1
            continue
        statements = render_alters(table, ttl, args.codec.strip(), args.cluster)
        print(f"-- {table.database}.{table.name}")
        for statement in statements:
            print(statement + ";")
            if args.apply:
                client.command(statement)
        planned += 1
    print(f"mode={'apply' if args.apply else 'dry-run'} planned={planned} skipped={skipped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
