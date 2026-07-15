#!/usr/bin/env python3
"""Plan or apply a TTL RECOMPRESS rule to ClickHouse MergeTree tables."""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import sys
import threading
import textwrap
import time
from dataclasses import dataclass

try:
    import clickhouse_connect
except ModuleNotFoundError:  # Allow --help without the optional dependency.
    clickhouse_connect = None


SYSTEM_DATABASES = {"system", "INFORMATION_SCHEMA", "information_schema"}
SUMMARY_TABLE_LIMIT = 20
DEFAULT_METADATA_BATCH_SIZE = 50
DEFAULT_APPLY_CONCURRENCY = 10
DEFAULT_MAX_ACTIVE_MATERIALIZE_TTL = 10
DEFAULT_MATERIALIZE_TTL_POLL_SECONDS = 5
_APPLY_THREAD_LOCAL = threading.local()


@dataclass(frozen=True)
class Table:
    database: str
    name: str
    create_query: str
    partition_key: str
    total_rows: int
    total_bytes: int


@dataclass(frozen=True)
class RankedTable:
    database: str
    name: str
    total_rows: int
    total_bytes: int


@dataclass(frozen=True)
class PlannedTable:
    table: Table
    ttl: str | None
    ttl_base: str | None
    reason: str | None


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


def has_ttl_move(ttl: str) -> bool:
    return re.search(r"\bTO\s+(?:VOLUME|DISK)\b", ttl, re.IGNORECASE) is not None


def split_function_call(expression: str) -> tuple[str, str] | None:
    expression = expression.strip()
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression)
    if not match or not expression.endswith(")"):
        return None
    open_index = expression.find("(")
    close_index = len(expression) - 1
    depth = 0
    quote = ""
    for index, char in enumerate(expression[open_index:], start=open_index):
        if quote:
            if char == "\\":
                continue
            if char == quote:
                quote = ""
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != close_index:
                return None
    return match.group(1), expression[open_index + 1 : close_index].strip()


def first_function_argument(arguments: str) -> str | None:
    depth = 0
    quote = ""
    for index, char in enumerate(arguments):
        if quote:
            if char == "\\":
                continue
            if char == quote:
                quote = ""
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            value = arguments[:index].strip()
            return value or None
    value = arguments.strip()
    return value or None


def unquote_identifier(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1].replace("``", "`")
    return value


def is_simple_identifier(value: str) -> bool:
    return re.fullmatch(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_]*", value.strip()) is not None


def extract_column_types(create_query: str) -> dict[str, str]:
    first_open = create_query.find("(")
    if first_open < 0:
        return {}
    depth = 0
    quote = ""
    close_index = -1
    for index, char in enumerate(create_query[first_open:], start=first_open):
        if quote:
            if char == "\\":
                continue
            if char == quote:
                quote = ""
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_index = index
                break
    if close_index < 0:
        return {}

    columns: dict[str, str] = {}
    body = create_query[first_open + 1 : close_index]
    for raw_line in body.splitlines():
        line = raw_line.strip().rstrip(",")
        if not line:
            continue
        match = re.match(r"`([^`]+)`\s+(.+)$", line) or re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$", line)
        if not match:
            continue
        name = match.group(1)
        column_type = match.group(2).split()[0]
        if name.upper() in {"INDEX", "KEY", "CONSTRAINT", "PROJECTION"}:
            continue
        columns[name] = column_type
    return columns


def normalized_column_type(column_type: str | None) -> str:
    if column_type is None:
        return ""
    normalized = column_type.lower()
    while True:
        if normalized.startswith("nullable(") and normalized.endswith(")"):
            normalized = normalized[len("nullable(") : -1]
            continue
        if normalized.startswith("lowcardinality(") and normalized.endswith(")"):
            normalized = normalized[len("lowcardinality(") : -1]
            continue
        return normalized


def is_date_like_type(column_type: str | None) -> bool:
    normalized = normalized_column_type(column_type)
    return normalized.startswith(("date", "datetime"))


def is_datetime64_type(column_type: str | None) -> bool:
    return normalized_column_type(column_type).startswith("datetime64")


def ttl_compatible_expression(expression: str, column_types: dict[str, str]) -> str:
    value = expression.strip()
    call = split_function_call(value)
    if call is not None:
        function, arguments = call
        normalized = function.lower()
        first_argument = first_function_argument(arguments)
        if normalized == "todatetime64":
            return f"toDateTime({value})"
        if normalized.startswith("tostartof") and first_argument:
            argument_type = column_types.get(unquote_identifier(first_argument)) if is_simple_identifier(first_argument) else None
            if is_datetime64_type(argument_type):
                return f"toDateTime({value})"
        return value
    if is_simple_identifier(value) and is_datetime64_type(column_types.get(unquote_identifier(value))):
        return f"toDateTime({value})"
    return value


def ttl_base_expression(partition_key: str, column_types: dict[str, str]) -> str | None:
    value = partition_key.strip()
    if not value:
        return None
    call = split_function_call(value)
    if call is None:
        if is_simple_identifier(value) and is_date_like_type(column_types.get(unquote_identifier(value))):
            return ttl_compatible_expression(value, column_types)
        return None
    function, arguments = call
    normalized = function.lower()
    if normalized in {
        "toyyyymm",
        "toyyyymmdd",
        "toyyyymmddhhmmss",
        "toyear",
        "toquarter",
        "tomonth",
        "todayofmonth",
        "tohour",
    }:
        first_argument = first_function_argument(arguments)
        return ttl_compatible_expression(first_argument, column_types) if first_argument else None
    if normalized.startswith("tostartof") or normalized in {"tomonday", "todate", "todatetime", "todatetime64"}:
        return ttl_compatible_expression(value, column_types)
    return None


def render_alters(
    table: Table,
    ttl: str | None,
    ttl_base: str,
    codec: str,
    cluster: str | None,
    materialize_ttl_after_modify: bool,
) -> list[str]:
    on_cluster = f" ON CLUSTER {quote_ident(cluster)}" if cluster else ""
    new_rule = f"{ttl_base} + INTERVAL 1 WEEK RECOMPRESS CODEC({codec})"
    full_ttl = f"{ttl}, {new_rule}" if ttl else new_rule
    ttl_statement = f"ALTER TABLE {qualified(table)}{on_cluster} MODIFY TTL {full_ttl}"
    if not materialize_ttl_after_modify:
        ttl_statement += "\nSETTINGS materialize_ttl_after_modify = 0"
    return [
        f"ALTER TABLE {qualified(table)}{on_cluster} MODIFY SETTING "
        "materialize_ttl_recalculate_only = true, merge_with_recompression_ttl_timeout = 1800",
        ttl_statement,
    ]


def csv_values(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def create_client(args: argparse.Namespace):
    return clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        secure=args.secure,
    )


def get_apply_client(args: argparse.Namespace):
    client = getattr(_APPLY_THREAD_LOCAL, "client", None)
    if client is None:
        client = create_client(args)
        _APPLY_THREAD_LOCAL.client = client
    return client


def fetch_ranked_tables(client, args: argparse.Namespace) -> list[RankedTable]:
    conditions = ["active"]
    databases = csv_values(args.databases)
    if databases:
        conditions.append("database IN (" + ", ".join(map(quote_literal, databases)) + ")")
    else:
        conditions.append("database NOT IN (" + ", ".join(map(quote_literal, sorted(SYSTEM_DATABASES))) + ")")
    tables = csv_values(args.tables)
    if tables:
        conditions.append("`table` IN (" + ", ".join(map(quote_literal, tables)) + ")")
    limit_clause = "" if args.all else f"\n        LIMIT {args.limit}"
    query = (
        """
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
        ORDER BY total_bytes DESC"""
        + limit_clause
        + """
        """
    )
    query = textwrap.dedent(query).strip()
    log_sql("fetch_parts", query)
    result = client.query(query)
    return [
        RankedTable(str(row[0]), str(row[1]), int(row[2]), int(row[3]))
        for row in result.result_rows
    ]


def chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_metadata_batch(
    client,
    database: str,
    names: list[str],
    log_query: bool = False,
) -> dict[tuple[str, str], tuple[str, str]]:
    query = (
        """
        SELECT
            database,
            name,
            create_table_query,
            partition_key
        FROM system.tables
        WHERE database = """
        + quote_literal(database)
        + """
          AND name IN ("""
        + ", ".join(map(quote_literal, names))
        + """)
          AND database NOT IN ("""
        + ", ".join(map(quote_literal, sorted(SYSTEM_DATABASES)))
        + """)
          AND engine LIKE '%MergeTree%'
        """
    )
    query = textwrap.dedent(query).strip()
    if log_query:
        log_sql("fetch_metadata", query)
    result = client.query(query)
    return {
        (str(row[0]), str(row[1])): (str(row[2]), str(row[3]))
        for row in result.result_rows
    }


def fetch_table_metadata(client, ranked: list[RankedTable], batch_size: int) -> dict[tuple[str, str], tuple[str, str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for table in ranked:
        grouped[table.database].append(table.name)

    metadata: dict[tuple[str, str], tuple[str, str]] = {}
    chunk_index = 0
    total_chunks = sum((len(names) + batch_size - 1) // batch_size for names in grouped.values())
    for database, names in grouped.items():
        for chunk in chunks(names, batch_size):
            chunk_index += 1
            log(
                "stage=fetch_metadata status=started "
                f"chunk={chunk_index}/{total_chunks} database={database} tables={len(chunk)}"
            )
            metadata.update(
                fetch_metadata_batch(
                    client,
                    database,
                    chunk,
                    log_query=chunk_index <= SUMMARY_TABLE_LIMIT,
                )
            )
            log(
                "stage=fetch_metadata status=completed "
                f"chunk={chunk_index}/{total_chunks} database={database} tables={len(chunk)}"
            )
    return metadata


def fetch_tables(client, args: argparse.Namespace) -> list[Table]:
    ranked = fetch_ranked_tables(client, args)
    metadata = fetch_table_metadata(client, ranked, args.metadata_batch_size)
    tables: list[Table] = []
    for index, table in enumerate(ranked, start=1):
        name = f"{table.database}.{table.name}"
        details = metadata.get((table.database, table.name))
        if details is None:
            log(f"stage=fetch_metadata status=skipped table={index}/{len(ranked)} name={name} reason=not MergeTree or missing metadata")
            continue
        create_query, partition_key = details
        tables.append(
            Table(
                table.database,
                table.name,
                create_query,
                partition_key,
                table.total_rows,
                table.total_bytes,
            )
        )
    return tables


def print_table_summary(title: str, tables: list[Table], limit: int = SUMMARY_TABLE_LIMIT) -> None:
    print(title)
    visible_tables = tables[:limit]
    for index, table in enumerate(visible_tables, start=1):
        print(
            f"  {index}. {table.database}.{table.name} "
            f"rows={table.total_rows} bytes={table.total_bytes} ({format_bytes(table.total_bytes)})"
        )
    if len(tables) > limit:
        print(f"  ... omitted {len(tables) - limit} more tables")
    print()


def plan_tables(tables: list[Table]) -> list[PlannedTable]:
    return [
        PlannedTable(table, ttl, ttl_base, skip_reason(table, ttl, ttl_base))
        for table in tables
        for ttl in [extract_ttl(table.create_query)]
        for ttl_base in [ttl_base_expression(table.partition_key, extract_column_types(table.create_query))]
    ]


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def log_sql(stage: str, sql: str) -> None:
    normalized = sql.strip()
    suffix = "" if normalized.endswith(";") else ";"
    log(f"stage={stage} sql=\n{normalized}{suffix}")


def skip_reason(table: Table, ttl: str | None, ttl_base: str | None) -> str | None:
    if not table.partition_key.strip():
        return "empty partition key"
    if ttl and has_recompress(ttl):
        return "already has TTL RECOMPRESS"
    if ttl and has_ttl_move(ttl):
        return "already has TTL MOVE"
    if ttl_base is None:
        return "unsupported partition key for TTL base expression"
    return None


def print_table_plan(
    index: int,
    table: Table,
    ttl: str | None,
    ttl_base: str | None,
    statements: list[str] | None,
    reason: str | None,
) -> None:
    print(f"-- [{index}] {table.database}.{table.name}")
    print(f"-- rows: {table.total_rows}")
    print(f"-- bytes: {table.total_bytes} ({format_bytes(table.total_bytes)})")
    print(f"-- current partition key: {table.partition_key or '(none)'}")
    print(f"-- TTL base expression: {ttl_base or '(none)'}")
    print(f"-- current table TTL: {ttl or '(none)'}")
    if reason:
        print(f"-- skip reason: {reason}")
    else:
        assert statements is not None
        print(f"-- planned setting: {statements[0]}")
        print(f"-- planned TTL: {statements[1]}")
    print()


def active_materialize_ttl_mutations(client) -> int:
    query = """
        SELECT count()
        FROM system.mutations
        WHERE is_done = 0
          AND positionCaseInsensitive(command, 'MATERIALIZE TTL') > 0
    """
    result = client.query(textwrap.dedent(query).strip())
    return int(result.result_rows[0][0])


def wait_for_materialize_ttl_capacity(client, max_active: int, poll_seconds: int) -> None:
    while True:
        active = active_materialize_ttl_mutations(client)
        if active < max_active:
            return
        log(
            "stage=apply status=waiting-materialize-ttl "
            f"active={active} limit={max_active} poll_seconds={poll_seconds}"
        )
        time.sleep(poll_seconds)


def apply_table(client, index: int, total: int, table: Table, statements: list[str], log_queries: bool) -> None:
    name = f"{table.database}.{table.name}"
    log(f"stage=apply status=setting-started table={index}/{total} name={name}")
    if log_queries:
        log_sql("apply", statements[0])
    try:
        client.command(statements[0])
    except Exception as error:
        log(f"stage=apply status=setting-failed table={index}/{total} name={name} error={error}")
        raise
    log(f"stage=apply status=setting-completed table={index}/{total} name={name}")
    wait_for_materialize_ttl_capacity(
        client,
        DEFAULT_MAX_ACTIVE_MATERIALIZE_TTL,
        DEFAULT_MATERIALIZE_TTL_POLL_SECONDS,
    )
    log(f"stage=apply status=ttl-started table={index}/{total} name={name}")
    if log_queries:
        log_sql("apply", statements[1])
    try:
        client.command(statements[1])
    except Exception as error:
        log(f"stage=apply status=ttl-failed table={index}/{total} name={name} error={error}")
        raise
    log(f"stage=apply status=ttl-completed table={index}/{total} name={name}")


def apply_table_with_thread_client(
    args: argparse.Namespace,
    index: int,
    total: int,
    table: Table,
    statements: list[str],
    log_queries: bool,
) -> int:
    apply_table(get_apply_client(args), index, total, table, statements, log_queries)
    return index


def apply_execution_plan(
    client,
    args: argparse.Namespace,
    execution_plan: list[tuple[Table, list[str]]],
) -> None:
    total = len(execution_plan)
    log(f"stage=apply status=started tables={total} concurrency={args.apply_concurrency}")
    if args.apply_concurrency == 1:
        for index, (table, statements) in enumerate(execution_plan, start=1):
            if index == SUMMARY_TABLE_LIMIT + 1:
                log(f"stage=apply sql=omitted remaining={total - SUMMARY_TABLE_LIMIT}")
            apply_table(client, index, total, table, statements, index <= SUMMARY_TABLE_LIMIT)
    else:
        with ThreadPoolExecutor(max_workers=args.apply_concurrency) as executor:
            plan_iter = iter(enumerate(execution_plan, start=1))
            futures = {}

            def submit_next() -> bool:
                try:
                    index, (table, statements) = next(plan_iter)
                except StopIteration:
                    return False
                future = executor.submit(
                    apply_table_with_thread_client,
                    args,
                    index,
                    total,
                    table,
                    statements,
                    index <= SUMMARY_TABLE_LIMIT,
                )
                futures[future] = index
                return True

            for _ in range(min(args.apply_concurrency, total)):
                submit_next()
            if total > SUMMARY_TABLE_LIMIT:
                log(f"stage=apply sql=omitted remaining={total - SUMMARY_TABLE_LIMIT}")
            while futures:
                for future in as_completed(list(futures)):
                    del futures[future]
                    try:
                        future.result()
                    except Exception:
                        for pending in futures:
                            pending.cancel()
                        raise
                    submit_next()
                    break
    log(f"stage=apply status=completed tables={total}")


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
    parser.add_argument("--all", action="store_true", help="Process all selected active tables instead of only --limit")
    parser.add_argument(
        "--metadata-batch-size",
        type=int,
        default=DEFAULT_METADATA_BATCH_SIZE,
        help=f"Tables per metadata query within one database; default: {DEFAULT_METADATA_BATCH_SIZE}",
    )
    parser.add_argument(
        "--apply-concurrency",
        type=int,
        default=DEFAULT_APPLY_CONCURRENCY,
        help=f"Maximum tables to ALTER concurrently; default: {DEFAULT_APPLY_CONCURRENCY}",
    )
    parser.add_argument(
        "--no-materialize-ttl-after-modify",
        dest="materialize_ttl_after_modify",
        action="store_false",
        default=True,
        help="Add query SETTINGS materialize_ttl_after_modify = 0 to MODIFY TTL to avoid automatic historical TTL materialization",
    )
    parser.add_argument("--apply", action="store_true", help="Execute the plan; default is dry-run")
    args = parser.parse_args(argv)
    if ";" in args.codec:
        parser.error("codec must not contain semicolons")
    if not args.codec.strip():
        parser.error("codec must not be empty")
    if args.limit <= 0:
        parser.error("limit must be positive")
    if args.metadata_batch_size <= 0:
        parser.error("metadata-batch-size must be positive")
    if args.apply_concurrency <= 0:
        parser.error("apply-concurrency must be positive")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if clickhouse_connect is None:
        print("missing dependency: pip install clickhouse-connect", file=sys.stderr)
        return 2
    client = create_client(args)
    limit_label = "all" if args.all else str(args.limit)
    log(
        "stage=fetch status=started "
        f"limit={limit_label} databases={args.databases or '(all non-system)'} "
        f"tables={args.tables or '(all)'}"
    )
    try:
        tables = fetch_tables(client, args)
    except Exception as error:
        log(f"stage=fetch status=failed error={error}")
        raise
    log(f"stage=fetch status=completed selected={len(tables)}")
    planned_tables = plan_tables(tables)
    eligible_tables = [planned.table for planned in planned_tables if planned.reason is None]
    print_table_summary(
        f"Active tables by bytes overall (limit={limit_label} selected={len(tables)} showing={min(len(tables), SUMMARY_TABLE_LIMIT)}):",
        tables,
    )
    print_table_summary(
        "Active tables by bytes excluding skipped tables "
        f"(overall_limit={limit_label} selected={len(eligible_tables)} showing={min(len(eligible_tables), SUMMARY_TABLE_LIMIT)}):",
        eligible_tables,
    )

    log(f"stage=plan status=started tables={len(tables)}")
    planned = skipped = 0
    execution_plan: list[tuple[Table, list[str]]] = []
    for index, planned_table in enumerate(planned_tables, start=1):
        table = planned_table.table
        log(f"stage=plan status=processing table={index}/{len(tables)} name={table.database}.{table.name}")
        if index == SUMMARY_TABLE_LIMIT + 1:
            print(f"-- omitted detailed plans for {len(planned_tables) - SUMMARY_TABLE_LIMIT} more tables")
            print()
        ttl = planned_table.ttl
        ttl_base = planned_table.ttl_base
        reason = planned_table.reason
        if reason:
            if index <= SUMMARY_TABLE_LIMIT:
                print_table_plan(index, table, ttl, ttl_base, None, reason)
            log(f"stage=plan status=skipped table={index}/{len(tables)} reason={reason}")
            skipped += 1
            continue
        assert ttl_base is not None
        statements = render_alters(
            table,
            ttl,
            ttl_base,
            args.codec.strip(),
            args.cluster,
            args.materialize_ttl_after_modify,
        )
        if index <= SUMMARY_TABLE_LIMIT:
            print_table_plan(index, table, ttl, ttl_base, statements, None)
        execution_plan.append((table, statements))
        planned += 1
    log(f"stage=plan status=completed planned={planned} skipped={skipped}")

    if args.apply:
        apply_execution_plan(client, args, execution_plan)
    else:
        log("stage=apply status=skipped reason=dry-run; rerun with --apply to execute")
    log(f"run status=completed mode={'apply' if args.apply else 'dry-run'} planned={planned} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
