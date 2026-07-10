#!/usr/bin/env python3
import argparse
import dataclasses
import re
import sys
import time
from pathlib import Path

try:
    import clickhouse_connect
except ModuleNotFoundError:
    clickhouse_connect = None


SYSTEM_DATABASES = {"system", "INFORMATION_SCHEMA", "information_schema"}
MODES = {"plan", "apply-ttl", "materialize", "resume-materialize", "optimize"}


@dataclasses.dataclass
class TableInfo:
    database: str
    name: str
    engine: str
    partition_key: str
    create_table_query: str
    total_rows: int
    total_bytes: int


@dataclasses.dataclass
class TablePlan:
    table: TableInfo
    recompress_expr: str
    current_ttl_entries: list[str]
    current_ttl_recompress_entries: list[str]
    current_ttl_delete_entries: list[str]
    current_ttl_other_entries: list[str]
    planned_ttl_entries: list[str]
    statements: list[str]
    current_ttl_state: str


@dataclasses.dataclass
class OptimizePlan:
    database: str
    table: str
    partition: str
    partition_id: str
    default_compression_codec: str
    bytes: int
    statement: str


@dataclasses.dataclass
class SkippedTable:
    database: str
    table: str
    reason: str


@dataclasses.dataclass
class MutationState:
    database: str
    table: str
    mutation_id: str
    command: str
    create_time: str
    is_done: int
    latest_fail_reason: str
    parts_to_do: int
    status: str


@dataclasses.dataclass
class CodecPartGroup:
    codec: str
    active_parts: int
    active_rows: int
    due_parts: int
    due_rows: int
    missing_ttl_info_parts: int
    missing_ttl_info_rows: int


@dataclasses.dataclass
class MaterializePrecheck:
    should_submit: bool
    reason: str
    target_codec: str
    active_parts: int
    active_rows: int
    target_codec_parts: int
    target_codec_rows: int
    due_parts: int
    due_rows: int
    due_non_target_parts: int
    due_non_target_rows: int
    missing_ttl_info_non_target_parts: int
    missing_ttl_info_non_target_rows: int
    codec_groups: list[CodecPartGroup]


def quote_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def quote_table(database: str, table: str) -> str:
    return f"{quote_identifier(database)}.{quote_identifier(table)}"


def quote_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def compact_sql_expression(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def normalize_codec_expression(value: str) -> str:
    compact = compact_sql_expression(value).upper()
    if compact.startswith("CODEC(") and compact.endswith(")"):
        return compact[len("CODEC(") : -1]
    return compact


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def unquote_filter_identifier(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        return value[1:-1].replace("``", "`")
    return value


def parse_table_filters(value: str | None) -> tuple[set[str], set[tuple[str, str]]]:
    unqualified = set()
    qualified = set()
    for item in split_csv(value):
        if "." in item:
            database, table = item.split(".", 1)
            qualified.add((unquote_filter_identifier(database), unquote_filter_identifier(table)))
        else:
            unqualified.add(unquote_filter_identifier(item))
    return unqualified, qualified


def table_filter_sql(
    table_argument: str | None,
    database_column: str = "database",
    table_column: str = "name",
) -> str | None:
    unqualified, qualified = parse_table_filters(table_argument)
    clauses = []
    if unqualified:
        clauses.append(f"{table_column} IN (" + ", ".join(quote_literal(name) for name in sorted(unqualified)) + ")")
    for database, table in sorted(qualified):
        clauses.append(
            f"({database_column} = {quote_literal(database)} AND {table_column} = {quote_literal(table)})"
        )
    if not clauses:
        return None
    return "(" + " OR ".join(clauses) + ")"


def get_client(args: argparse.Namespace):
    if clickhouse_connect is None:
        raise RuntimeError(
            "missing Python package 'clickhouse-connect'; install it with "
            "`python3 -m pip install clickhouse-connect`"
        )
    return clickhouse_connect.get_client(
        host=args.host,
        port=args.http_port,
        username=args.user,
        password=args.password,
        secure=args.secure,
        database=args.database,
    )


def query_rows(client, query: str) -> list[dict]:
    result = client.query(re.sub(r"\s+", " ", query.strip()))
    return list(result.named_results())


def command(client, query: str) -> None:
    client.command(query.strip())


def log(args: argparse.Namespace, message: str) -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] {message}"
    log_file = Path(args.output_dir) / args.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as out:
        out.write(line + "\n")
    if not getattr(args, "quiet", False):
        print(line, file=sys.stderr, flush=True)


def char_state_aware_scan(sql: str):
    depth = 0
    quote = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote and quote in {"'", '"', "`"}:
                    i += 2
                    continue
                quote = None
            yield i, ch, depth, quote
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        yield i, ch, depth, quote
        i += 1


def is_word_boundary(sql: str, start: int, end: int) -> bool:
    before = sql[start - 1] if start > 0 else " "
    after = sql[end] if end < len(sql) else " "
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def find_keyword_top_level(sql: str, keyword: str, start: int = 0) -> int:
    target = keyword.lower()
    lower = sql.lower()
    for i, _ch, depth, quote in char_state_aware_scan(sql):
        if i < start or depth != 0 or quote:
            continue
        end = i + len(target)
        if lower.startswith(target, i) and is_word_boundary(sql, i, end):
            return i
    return -1


def find_next_keyword_top_level(sql: str, keywords: list[str], start: int) -> int:
    lowered_keywords = [keyword.lower() for keyword in keywords]
    lower = sql.lower()
    for i, _ch, depth, quote in char_state_aware_scan(sql):
        if i < start or depth != 0 or quote:
            continue
        for keyword in lowered_keywords:
            end = i + len(keyword)
            if lower.startswith(keyword, i) and is_word_boundary(sql, i, end):
                return i
    return len(sql)


def find_matching_paren(sql: str, open_pos: int) -> int:
    if open_pos < 0 or open_pos >= len(sql) or sql[open_pos] != "(":
        return -1

    quote = None
    depth = 0
    i = open_pos
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote and quote in {"'", '"', "`"}:
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def split_top_level_commas(value: str) -> list[str]:
    result = []
    part_start = 0
    for i, ch, depth, quote in char_state_aware_scan(value):
        if ch == "," and depth == 0 and not quote:
            result.append(value[part_start:i].strip())
            part_start = i + 1
    result.append(value[part_start:].strip())
    return [item for item in result if item]


def extract_table_ttl_entries(create_table_query: str) -> tuple[list[str] | None, str | None]:
    ttl_pos = find_keyword_top_level(create_table_query, "TTL")
    if ttl_pos < 0:
        return None, "missing table-level TTL"

    start = ttl_pos + len("TTL")
    end = find_next_keyword_top_level(
        create_table_query,
        ["SETTINGS", "COMMENT", "AS", "EMPTY"],
        start,
    )
    ttl_text = create_table_query[start:end].strip()
    if not ttl_text:
        return None, "empty table-level TTL"
    return split_top_level_commas(ttl_text), None


def classify_ttl_entries(entries: list[str]) -> tuple[list[str], list[str], list[str]]:
    recompress_entries = []
    delete_entries = []
    other_entries = []

    for entry in entries:
        if re.search(r"\bRECOMPRESS\b", entry, flags=re.IGNORECASE):
            recompress_entries.append(entry)
        elif re.search(
            r"\bTO\s+(?:VOLUME|DISK)\b|\bGROUP\s+BY\b|\bDELETE\s+WHERE\b|\bWHERE\b",
            entry,
            flags=re.IGNORECASE,
        ):
            other_entries.append(entry)
        else:
            delete_entries.append(entry)

    return recompress_entries, delete_entries, other_entries


def extract_recompress_codec(entry: str) -> str | None:
    recompress_pos = find_keyword_top_level(entry, "RECOMPRESS")
    if recompress_pos < 0:
        return None
    codec_pos = find_keyword_top_level(entry, "CODEC", recompress_pos + len("RECOMPRESS"))
    if codec_pos < 0:
        return None
    open_pos = entry.find("(", codec_pos + len("CODEC"))
    close_pos = find_matching_paren(entry, open_pos)
    if close_pos < 0:
        return None
    return entry[open_pos + 1 : close_pos].strip()


def materialize_target_codec(args: argparse.Namespace, plan: TablePlan) -> str | None:
    if len(plan.current_ttl_recompress_entries) != 1:
        return None
    return extract_recompress_codec(plan.current_ttl_recompress_entries[0]) or args.codec


def classify_ttl_state(
    ttl_entries: list[str] | None,
    recompress_entries: list[str],
    other_entries: list[str],
) -> str:
    if ttl_entries is None:
        return "missing table-level TTL"
    if recompress_entries:
        return "already has recompression TTL"
    if other_entries:
        return "has unsupported table-level TTL entries"
    return "delete-only table-level TTL"


def unsupported_ttl_reason(entry: str) -> str:
    if re.search(r"\bTO\s+VOLUME\b", entry, flags=re.IGNORECASE):
        return f"existing TTL entry is a MOVE TO VOLUME rule: {entry}"
    if re.search(r"\bTO\s+DISK\b", entry, flags=re.IGNORECASE):
        return f"existing TTL entry is a MOVE TO DISK rule: {entry}"
    if re.search(r"\bGROUP\s+BY\b", entry, flags=re.IGNORECASE):
        return f"existing TTL entry is an aggregation rule: {entry}"
    if re.search(r"\bDELETE\s+WHERE\b|\bWHERE\b", entry, flags=re.IGNORECASE):
        return f"existing TTL entry is a conditional delete rule: {entry}"
    return f"existing TTL entry is not supported in v1: {entry}"


def partition_key_kind(partition_key: str) -> str | None:
    if re.search(r"\b(?:toMonday|toStartOfWeek)\s*\(", partition_key, flags=re.IGNORECASE):
        return "week"
    if re.search(r"\b(?:toDate|toStartOfDay)\s*\(", partition_key, flags=re.IGNORECASE):
        return "day"
    return None


def infer_recompress_expr(args: argparse.Namespace, partition_key: str) -> tuple[str | None, str | None]:
    kind = partition_key_kind(partition_key)
    if kind == "week":
        return f"{partition_key} + INTERVAL {args.weekly_hot_weeks} WEEK", None
    if kind == "day":
        return f"{partition_key} + INTERVAL {args.daily_hot_days} DAY", None
    return None, f"unsupported Date-like partition key: {partition_key}"


def fetch_tables(client, args: argparse.Namespace) -> list[TableInfo]:
    included = set(split_csv(args.dbs))
    excluded = SYSTEM_DATABASES | set(split_csv(args.dbs_exclude))

    where = ["engine LIKE '%MergeTree%'"]
    if included:
        where.append("database IN (" + ", ".join(quote_literal(db) for db in sorted(included)) + ")")
    if excluded:
        where.append("database NOT IN (" + ", ".join(quote_literal(db) for db in sorted(excluded)) + ")")
    table_filter = table_filter_sql(args.tables)
    if table_filter:
        where.append(table_filter)

    query = f"""
        SELECT
            database,
            name,
            engine,
            partition_key,
            create_table_query,
            total_rows,
            total_bytes
        FROM system.tables
        WHERE {' AND '.join(where)}
        ORDER BY database, name
    """
    rows = query_rows(client, query)
    return [
        TableInfo(
            database=str(row["database"]),
            name=str(row["name"]),
            engine=str(row["engine"]),
            partition_key=str(row.get("partition_key") or ""),
            create_table_query=str(row.get("create_table_query") or ""),
            total_rows=int(row.get("total_rows") or 0),
            total_bytes=int(row.get("total_bytes") or 0),
        )
        for row in rows
    ]


def build_plan_for_table(args: argparse.Namespace, table: TableInfo) -> tuple[TablePlan | None, str | None]:
    ttl_entries, ttl_error = extract_table_ttl_entries(table.create_table_query)
    if ttl_error == "empty table-level TTL":
        return None, ttl_error

    current_ttl_entries = ttl_entries or []
    current_ttl_recompress_entries, current_ttl_delete_entries, current_ttl_other_entries = classify_ttl_entries(
        current_ttl_entries
    )
    current_ttl_state = classify_ttl_state(ttl_entries, current_ttl_recompress_entries, current_ttl_other_entries)

    if current_ttl_recompress_entries:
        return None, "already has recompression TTL"
    if current_ttl_other_entries:
        return None, unsupported_ttl_reason(current_ttl_other_entries[0])

    recompress_expr, error = infer_recompress_expr(args, table.partition_key)
    if error:
        return None, error

    planned_ttl_entries = [f"{recompress_expr} RECOMPRESS CODEC({args.codec})", *current_ttl_delete_entries]
    statement = (
        "ALTER TABLE "
        + quote_table(table.database, table.name)
        + " MODIFY TTL\n    "
        + ",\n    ".join(planned_ttl_entries)
    )

    return (
        TablePlan(
            table=table,
            recompress_expr=recompress_expr,
            current_ttl_entries=current_ttl_entries,
            current_ttl_recompress_entries=current_ttl_recompress_entries,
            current_ttl_delete_entries=current_ttl_delete_entries,
            current_ttl_other_entries=current_ttl_other_entries,
            planned_ttl_entries=planned_ttl_entries,
            statements=[statement],
            current_ttl_state=current_ttl_state,
        ),
        None,
    )


def build_materialize_plan_for_table(table: TableInfo) -> tuple[TablePlan | None, str | None]:
    ttl_entries, ttl_error = extract_table_ttl_entries(table.create_table_query)
    if ttl_error:
        return None, ttl_error

    current_ttl_recompress_entries, current_ttl_delete_entries, current_ttl_other_entries = classify_ttl_entries(
        ttl_entries or []
    )
    if not current_ttl_recompress_entries:
        return None, "TTL does not contain RECOMPRESS"

    return (
        TablePlan(
            table=table,
            recompress_expr="existing TTL RECOMPRESS expression",
            current_ttl_entries=ttl_entries or [],
            current_ttl_recompress_entries=current_ttl_recompress_entries,
            current_ttl_delete_entries=current_ttl_delete_entries,
            current_ttl_other_entries=current_ttl_other_entries,
            planned_ttl_entries=[],
            statements=[],
            current_ttl_state="present",
        ),
        None,
    )


def materialize_statement(args: argparse.Namespace, plan: TablePlan) -> str:
    return (
        f"ALTER TABLE {quote_table(plan.table.database, plan.table.name)} "
        f"MATERIALIZE TTL SETTINGS mutations_sync = {args.mutations_sync}"
    )


def ttl_statement(plan: TablePlan) -> str:
    return plan.statements[0]


def recalculate_only_setting_statement(plan: TablePlan) -> str:
    return (
        f"ALTER TABLE {quote_table(plan.table.database, plan.table.name)} "
        "MODIFY SETTING materialize_ttl_recalculate_only = true"
    )


def write_skip_report(args: argparse.Namespace, skipped: list[SkippedTable]) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    skipped_tsv = output_dir / args.skip_report
    skipped_tsv.write_text(
        "database\ttable\treason\n"
        + "".join(f"{item.database}\t{item.table}\t{item.reason}\n" for item in skipped),
        encoding="utf-8",
    )


def select_batch(args: argparse.Namespace, plans: list[TablePlan]) -> list[TablePlan]:
    if args.all_batches:
        return plans
    start = args.batch * args.batch_size
    end = start + args.batch_size
    return plans[start:end]


def format_readable_size(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def print_processing_summary(plans: list[TablePlan]) -> None:
    by_db: dict[str, list[TablePlan]] = {}
    for plan in plans:
        by_db.setdefault(plan.table.database, []).append(plan)

    total_rows = sum(plan.table.total_rows for plan in plans)
    total_bytes = sum(plan.table.total_bytes for plan in plans)
    print(
        "Processing summary: "
        f"databases={len(by_db)}, tables={len(plans)}, rows={total_rows}, "
        f"size={format_readable_size(total_bytes)}"
    )
    if not by_db:
        return

    print("Database processing order by size desc:")
    for index, (database, db_plans) in enumerate(database_plan_order(by_db), start=1):
        db_rows = sum(plan.table.total_rows for plan in db_plans)
        db_bytes = sum(plan.table.total_bytes for plan in db_plans)
        print(
            f"  {index}. {database}: tables={len(db_plans)}, rows={db_rows}, "
            f"size={format_readable_size(db_bytes)}"
        )
    print()


def database_plan_order(by_db: dict[str, list[TablePlan]]) -> list[tuple[str, list[TablePlan]]]:
    return sorted(
        by_db.items(),
        key=lambda item: (
            -sum(plan.table.total_bytes for plan in item[1]),
            item[0],
        ),
    )


def sort_plans_by_database_size(plans: list[TablePlan]) -> list[TablePlan]:
    db_bytes: dict[str, int] = {}
    for plan in plans:
        db_bytes[plan.table.database] = db_bytes.get(plan.table.database, 0) + plan.table.total_bytes
    return sorted(
        plans,
        key=lambda plan: (
            -db_bytes[plan.table.database],
            plan.table.database,
            plan.table.name,
        ),
    )


def print_entries(indent: str, entries: list[str]) -> None:
    if not entries:
        print(f"{indent}(none)")
        return
    for entry in entries:
        print(f"{indent}{entry}")


def execute_ttl_batch(client, batch: list[TablePlan]) -> None:
    for plan in batch:
        print(
            "Enabling materialize_ttl_recalculate_only "
            f"{plan.table.database}.{plan.table.name}",
            flush=True,
        )
        command(client, recalculate_only_setting_statement(plan))
        print(
            "Applying replicated TTL metadata ALTER "
            f"{plan.table.database}.{plan.table.name}",
            flush=True,
        )
        command(client, ttl_statement(plan))


def optimize_statement(plan: OptimizePlan) -> str:
    return (
        f"OPTIMIZE TABLE {quote_table(plan.database, plan.table)} "
        f"PARTITION ID {quote_literal(plan.partition_id)} FINAL"
    )


def fetch_optimize_plans(client, args: argparse.Namespace) -> list[OptimizePlan]:
    included = set(split_csv(args.dbs))
    excluded = SYSTEM_DATABASES | set(split_csv(args.dbs_exclude))

    filters = ["active"]
    if included:
        filters.append("database IN (" + ", ".join(quote_literal(db) for db in sorted(included)) + ")")
    if excluded:
        filters.append("database NOT IN (" + ", ".join(quote_literal(db) for db in sorted(excluded)) + ")")
    table_filter = table_filter_sql(args.tables, table_column="`table`")
    if table_filter:
        filters.append(table_filter)

    rows = query_rows(
        client,
        f"""
        SELECT
            database,
            `table`,
            partition,
            partition_id,
            default_compression_codec,
            sum(bytes) AS bys
        FROM system.parts
        WHERE {' AND '.join(filters)}
        GROUP BY
            database,
            `table`,
            partition,
            partition_id,
            default_compression_codec
        ORDER BY bys DESC
        LIMIT {args.optimize_limit}
        """,
    )
    plans = []
    seen_partitions: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (
            str(row.get("database") or ""),
            str(row.get("table") or ""),
            str(row.get("partition_id") or ""),
        )
        if key in seen_partitions:
            continue
        seen_partitions.add(key)
        plan = OptimizePlan(
            database=key[0],
            table=key[1],
            partition=str(row.get("partition") or ""),
            partition_id=key[2],
            default_compression_codec=str(row.get("default_compression_codec") or ""),
            bytes=int(row.get("bys") or 0),
            statement="",
        )
        plans.append(dataclasses.replace(plan, statement=optimize_statement(plan)))
    return plans


def execute_optimize_plans(client, plans: list[OptimizePlan]) -> None:
    for index, plan in enumerate(plans, start=1):
        print(
            "Optimizing "
            f"{index}/{len(plans)} {plan.database}.{plan.table} "
            f"partition_id={plan.partition_id}, size={format_readable_size(plan.bytes)}",
            flush=True,
        )
        command(client, plan.statement)


def mutation_status(row: dict) -> str:
    if row.get("latest_fail_reason"):
        return "failed"
    if int(row.get("is_done") or 0):
        return "done"
    return "queued"


def row_to_mutation_state(database: str, table: str, row: dict, status: str | None = None) -> MutationState:
    return MutationState(
        database=database,
        table=table,
        mutation_id=str(row.get("mutation_id") or ""),
        command=str(row.get("command") or ""),
        create_time=str(row.get("create_time") or ""),
        is_done=int(row.get("is_done") or 0),
        latest_fail_reason=str(row.get("latest_fail_reason") or ""),
        parts_to_do=int(row.get("parts_to_do") or 0),
        status=status or mutation_status(row),
    )


def query_materialize_mutations(
    client,
    database: str,
    table: str,
    mutation_id: str | None = None,
    pending_only: bool = False,
) -> list[MutationState]:
    filters = [
        f"database = {quote_literal(database)}",
        f"table = {quote_literal(table)}",
        "command LIKE '%MATERIALIZE TTL%'",
    ]
    if mutation_id:
        filters.append(f"mutation_id = {quote_literal(mutation_id)}")
    if pending_only:
        filters.append("is_done = 0")

    rows = query_rows(
        client,
        f"""
        SELECT
            mutation_id,
            command,
            toString(create_time) AS create_time,
            is_done,
            latest_fail_reason,
            parts_to_do
        FROM system.mutations
        WHERE {' AND '.join(filters)}
        ORDER BY create_time DESC, mutation_id DESC
        """,
    )
    return [row_to_mutation_state(database, table, row) for row in rows]


def latest_materialize_mutation(client, database: str, table: str) -> MutationState | None:
    states = query_materialize_mutations(client, database, table)
    return states[0] if states else None


def pending_materialize_mutation(client, database: str, table: str) -> MutationState | None:
    states = query_materialize_mutations(client, database, table, pending_only=True)
    return states[0] if states else None


def materialize_precheck(client, args: argparse.Namespace, plan: TablePlan) -> MaterializePrecheck:
    database = plan.table.database
    table = plan.table.name
    target_codec = materialize_target_codec(args, plan)
    if target_codec is None:
        return MaterializePrecheck(
            should_submit=True,
            reason=(
                "cannot safely precheck tables with "
                f"{len(plan.current_ttl_recompress_entries)} RECOMPRESS TTL entries"
            ),
            target_codec="",
            active_parts=0,
            active_rows=0,
            target_codec_parts=0,
            target_codec_rows=0,
            due_parts=0,
            due_rows=0,
            due_non_target_parts=0,
            due_non_target_rows=0,
            missing_ttl_info_non_target_parts=0,
            missing_ttl_info_non_target_rows=0,
            codec_groups=[],
        )

    rows = query_rows(
        client,
        f"""
        SELECT
            default_compression_codec AS codec,
            count() AS active_parts,
            sum(rows) AS active_rows,
            countIf(arrayExists(x -> x <= now(), `recompression_ttl_info.max`)) AS due_parts,
            sumIf(rows, arrayExists(x -> x <= now(), `recompression_ttl_info.max`)) AS due_rows,
            countIf(empty(`recompression_ttl_info.max`)) AS missing_ttl_info_parts,
            sumIf(rows, empty(`recompression_ttl_info.max`)) AS missing_ttl_info_rows
        FROM system.parts
        WHERE database = {quote_literal(database)}
          AND table = {quote_literal(table)}
          AND active
        GROUP BY codec
        ORDER BY active_parts DESC, codec
        """,
    )

    groups = [
        CodecPartGroup(
            codec=str(row.get("codec") or ""),
            active_parts=int(row.get("active_parts") or 0),
            active_rows=int(row.get("active_rows") or 0),
            due_parts=int(row.get("due_parts") or 0),
            due_rows=int(row.get("due_rows") or 0),
            missing_ttl_info_parts=int(row.get("missing_ttl_info_parts") or 0),
            missing_ttl_info_rows=int(row.get("missing_ttl_info_rows") or 0),
        )
        for row in rows
    ]

    normalized_target = normalize_codec_expression(target_codec)
    active_parts = sum(group.active_parts for group in groups)
    active_rows = sum(group.active_rows for group in groups)
    target_codec_parts = sum(
        group.active_parts
        for group in groups
        if normalize_codec_expression(group.codec) == normalized_target
    )
    target_codec_rows = sum(
        group.active_rows
        for group in groups
        if normalize_codec_expression(group.codec) == normalized_target
    )
    due_parts = sum(group.due_parts for group in groups)
    due_rows = sum(group.due_rows for group in groups)
    due_non_target_parts = sum(
        group.due_parts
        for group in groups
        if normalize_codec_expression(group.codec) != normalized_target
    )
    due_non_target_rows = sum(
        group.due_rows
        for group in groups
        if normalize_codec_expression(group.codec) != normalized_target
    )
    missing_ttl_info_non_target_parts = sum(
        group.missing_ttl_info_parts
        for group in groups
        if normalize_codec_expression(group.codec) != normalized_target
    )
    missing_ttl_info_non_target_rows = sum(
        group.missing_ttl_info_rows
        for group in groups
        if normalize_codec_expression(group.codec) != normalized_target
    )

    if active_parts == 0:
        should_submit = False
        reason = "table has no active parts"
    elif target_codec_parts > 0:
        should_submit = False
        reason = (
            "active parts already include target codec "
            f"{target_codec}; skip to avoid duplicate MATERIALIZE TTL: "
            f"parts={target_codec_parts}, rows={target_codec_rows}"
        )
    elif due_non_target_parts > 0:
        should_submit = True
        reason = (
            "active parts with expired recompression TTL still use a non-target codec: "
            f"parts={due_non_target_parts}, rows={due_non_target_rows}, target={target_codec}"
        )
    elif missing_ttl_info_non_target_parts > 0:
        should_submit = True
        reason = (
            "active non-target parts have no recompression TTL info; "
            "MATERIALIZE TTL is needed to calculate and apply current TTL metadata: "
            f"parts={missing_ttl_info_non_target_parts}, rows={missing_ttl_info_non_target_rows}, "
            f"target={target_codec}"
        )
    elif due_parts == 0:
        should_submit = False
        reason = "no active parts have expired recompression TTL"
    else:
        should_submit = False
        reason = (
            "all active parts with expired recompression TTL already use target codec "
            f"{target_codec}: parts={due_parts}, rows={due_rows}"
        )

    return MaterializePrecheck(
        should_submit=should_submit,
        reason=reason,
        target_codec=target_codec,
        active_parts=active_parts,
        active_rows=active_rows,
        target_codec_parts=target_codec_parts,
        target_codec_rows=target_codec_rows,
        due_parts=due_parts,
        due_rows=due_rows,
        due_non_target_parts=due_non_target_parts,
        due_non_target_rows=due_non_target_rows,
        missing_ttl_info_non_target_parts=missing_ttl_info_non_target_parts,
        missing_ttl_info_non_target_rows=missing_ttl_info_non_target_rows,
        codec_groups=groups,
    )


def skipped_materialize_state(plan: TablePlan, reason: str) -> MutationState:
    return MutationState(
        database=plan.table.database,
        table=plan.table.name,
        mutation_id="",
        command="MATERIALIZE TTL",
        create_time="",
        is_done=1,
        latest_fail_reason=reason,
        parts_to_do=0,
        status="skipped",
    )


def new_materialize_mutation(client, database: str, table: str, before_ids: set[str]) -> MutationState | None:
    for state in query_materialize_mutations(client, database, table):
        if state.mutation_id not in before_ids:
            return state
    return None


def new_materialize_mutation_after_command_error(
    client,
    args: argparse.Namespace,
    database: str,
    table: str,
    before_ids: set[str],
) -> MutationState | None:
    try:
        return new_materialize_mutation(client, database, table, before_ids)
    except Exception as exc:
        log(
            args,
            "Could not inspect system.mutations on the existing connection after "
            f"MATERIALIZE TTL error for {database}.{table}: {exc}; retrying with a new connection",
        )

    try:
        fresh_client = get_client(args)
        return new_materialize_mutation(fresh_client, database, table, before_ids)
    except Exception as exc:
        log(
            args,
            "Could not inspect system.mutations on a new connection after "
            f"MATERIALIZE TTL error for {database}.{table}: {exc}",
        )
        return None


def submit_materialize(client, args: argparse.Namespace, plan: TablePlan) -> MutationState:
    database = plan.table.database
    table = plan.table.name
    existing = pending_materialize_mutation(client, database, table)
    if existing:
        print(f"Reusing pending mutation {database}.{table}: {existing.mutation_id}", flush=True)
        return existing

    before_ids = {state.mutation_id for state in query_materialize_mutations(client, database, table)}
    statement = materialize_statement(args, plan)
    print(f"Submitting MATERIALIZE TTL {database}.{table}", flush=True)
    try:
        command(client, statement)
    except Exception as exc:
        created = new_materialize_mutation_after_command_error(client, args, database, table, before_ids)
        if created:
            print(
                "MATERIALIZE TTL command returned an error after creating mutation "
                f"{database}.{table}: {exc}",
                flush=True,
            )
            return created
        raise
    created = new_materialize_mutation(client, database, table, before_ids)
    if created:
        return created
    latest = latest_materialize_mutation(client, database, table)
    if latest:
        return latest
    return MutationState(
        database=database,
        table=table,
        mutation_id="",
        command="MATERIALIZE TTL",
        create_time="",
        is_done=0,
        latest_fail_reason="",
        parts_to_do=0,
        status="unknown",
    )


def wait_for_materialize_submit_capacity(client, args: argparse.Namespace) -> None:
    deadline = time.monotonic() + args.materialize_timeout_seconds
    while True:
        pending = fetch_pending_materialize_states(client, args)
        if len(pending) < args.max_pending_materialize:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "timed out waiting for MATERIALIZE TTL mutation queue capacity; "
                f"pending={len(pending)}, max_pending={args.max_pending_materialize}"
            )
        log(
            args,
            "Waiting before submitting next MATERIALIZE TTL; "
            f"pending={len(pending)}, max_pending={args.max_pending_materialize}, "
            f"parts_to_do={sum(state.parts_to_do for state in pending)}",
        )
        time.sleep(args.materialize_poll_seconds)


def refresh_materialize_states(client, states: list[MutationState]) -> list[MutationState]:
    refreshed = []
    for state in states:
        if not state.mutation_id:
            refreshed.append(state)
            continue
        rows = query_materialize_mutations(client, state.database, state.table, mutation_id=state.mutation_id)
        refreshed.append(rows[0] if rows else dataclasses.replace(state, status="unknown"))
    return refreshed


def wait_for_materialize(client, args: argparse.Namespace, states: list[MutationState]) -> list[MutationState]:
    deadline = time.monotonic() + args.materialize_timeout_seconds
    current = states
    while True:
        current = refresh_materialize_states(client, current)
        unfinished = [state for state in current if state.status == "queued"]
        if not unfinished:
            log(args, "All MATERIALIZE TTL mutations finished")
            return current
        if time.monotonic() >= deadline:
            log(args, f"MATERIALIZE TTL wait timed out with {len(unfinished)} queued mutations")
            return [
                dataclasses.replace(state, status="timeout") if state.status == "queued" else state
                for state in current
            ]
        log(
            args,
            "Waiting for MATERIALIZE TTL mutations; "
            f"queued={len(unfinished)}, parts_to_do={sum(state.parts_to_do for state in unfinished)}",
        )
        time.sleep(args.materialize_poll_seconds)


def fetch_pending_materialize_states(client, args: argparse.Namespace) -> list[MutationState]:
    included = set(split_csv(args.dbs))
    excluded = SYSTEM_DATABASES | set(split_csv(args.dbs_exclude))

    filters = ["command LIKE '%MATERIALIZE TTL%'", "is_done = 0"]
    if included:
        filters.append("database IN (" + ", ".join(quote_literal(db) for db in sorted(included)) + ")")
    if excluded:
        filters.append("database NOT IN (" + ", ".join(quote_literal(db) for db in sorted(excluded)) + ")")
    table_filter = table_filter_sql(args.tables, table_column="table")
    if table_filter:
        filters.append(table_filter)

    rows = query_rows(
        client,
        f"""
        SELECT
            database,
            `table`,
            mutation_id,
            command,
            toString(create_time) AS create_time,
            is_done,
            latest_fail_reason,
            parts_to_do
        FROM system.mutations
        WHERE {' AND '.join(filters)}
        ORDER BY database, table, create_time DESC, mutation_id DESC
        """,
    )
    return [
        row_to_mutation_state(
            str(row.get("database") or ""),
            str(row.get("table") or ""),
            row,
        )
        for row in rows
    ]


def execute_materialize_batch(client, args: argparse.Namespace, batch: list[TablePlan]) -> list[MutationState]:
    if args.mode == "resume-materialize":
        log(args, "Scanning system.mutations for pending MATERIALIZE TTL mutations")
        states = fetch_pending_materialize_states(client, args)
    else:
        log(
            args,
            "Submitting MATERIALIZE TTL serially; "
            f"tables={len(batch)}, max_pending={args.max_pending_materialize}",
        )
        states = []
        for index, plan in enumerate(batch, start=1):
            existing = pending_materialize_mutation(client, plan.table.database, plan.table.name)
            if existing:
                log(
                    args,
                    "Reusing existing pending MATERIALIZE TTL "
                    f"{index}/{len(batch)} for {plan.table.database}.{plan.table.name}: {existing.mutation_id}",
                )
                states.append(existing)
                continue
            precheck = materialize_precheck(client, args, plan)
            log(
                args,
                "MATERIALIZE TTL precheck "
                f"{index}/{len(batch)} for {plan.table.database}.{plan.table.name}: "
                f"{precheck.reason}; active_parts={precheck.active_parts}, "
                f"target_codec_parts={precheck.target_codec_parts}, due_parts={precheck.due_parts}, "
                f"due_non_target_parts={precheck.due_non_target_parts}, "
                f"missing_ttl_info_non_target_parts={precheck.missing_ttl_info_non_target_parts}",
            )
            if not precheck.should_submit:
                states.append(skipped_materialize_state(plan, precheck.reason))
                continue
            wait_for_materialize_submit_capacity(client, args)
            log(args, f"Submitting MATERIALIZE TTL {index}/{len(batch)}")
            states.append(submit_materialize(client, args, plan))
    if args.wait_materialize:
        log(args, f"Polling MATERIALIZE TTL state for up to {args.materialize_timeout_seconds} seconds")
        states = wait_for_materialize(client, args, states)
    return states


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or execute ClickHouse table-level TTL RECOMPRESS ALTERs."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8123)
    parser.add_argument("--user", default="default")
    parser.add_argument("--password", default="")
    parser.add_argument("--secure", action="store_true")
    parser.add_argument("--database", default=None, help="Default database for the connection.")
    parser.add_argument("--dbs", help="Comma-separated databases to include. Defaults to all non-system databases.")
    parser.add_argument("--dbs-exclude", help="Comma-separated databases to exclude.")
    parser.add_argument(
        "--tables",
        help=(
            "Comma-separated tables to include. Supports unqualified table names or qualified db.table names."
        ),
    )
    parser.add_argument(
        "--codec",
        default="ZSTD(4)",
        help=(
            "ClickHouse codec expression used inside RECOMPRESS CODEC(...), "
            "for example LZ4, LZ4HC(9), or ZSTD(4). Default: ZSTD(4)."
        ),
    )
    parser.add_argument("--weekly-hot-weeks", type=int, default=1)
    parser.add_argument("--daily-hot-days", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--batch", type=int, default=0)
    parser.add_argument("--all-batches", action="store_true", help="Process all planned tables instead of only one batch.")
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="plan",
        help=(
            "Execution mode. plan is dry-run; apply-ttl submits replicated TTL metadata ALTER; "
            "materialize submits MATERIALIZE TTL; resume-materialize only watches existing MATERIALIZE TTL mutations; "
            "optimize optimizes the largest active system.parts partitions."
        ),
    )
    parser.add_argument("--output-dir", default=".", help="Directory for run log and skip report.")
    parser.add_argument("--log-file", default="ttl_recompress.log")
    parser.add_argument("--skip-report", default="ttl_recompress_skipped.tsv")
    parser.add_argument(
        "--mutations-sync",
        type=int,
        default=0,
        help=(
            "Value for MATERIALIZE TTL mutations_sync. Default 0 submits asynchronously; "
            "use --wait-materialize for client-side polling."
        ),
    )
    parser.add_argument("--wait-materialize", action="store_true")
    parser.add_argument(
        "--max-pending-materialize",
        type=int,
        default=1,
        help="Maximum pending MATERIALIZE TTL mutations before submitting the next table.",
    )
    parser.add_argument("--materialize-timeout-seconds", type=int, default=3600)
    parser.add_argument("--materialize-poll-seconds", type=float, default=5.0)
    parser.add_argument(
        "--optimize-limit",
        type=int,
        default=20,
        help="Number of largest system.parts partition/codec groups to optimize in --mode optimize.",
    )
    parser.add_argument("--log-every", type=int, default=100, help="Print scan progress every N tables. Use 0 to disable.")
    parser.add_argument("--quiet", action="store_true", help="Disable progress logs.")
    args = parser.parse_args(argv)
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.batch < 0:
        parser.error("--batch must be non-negative")
    if args.weekly_hot_weeks <= 0:
        parser.error("--weekly-hot-weeks must be positive")
    if args.daily_hot_days <= 0:
        parser.error("--daily-hot-days must be positive")
    if args.mutations_sync not in {0, 1, 2}:
        parser.error("--mutations-sync must be 0, 1, or 2")
    if args.max_pending_materialize <= 0:
        parser.error("--max-pending-materialize must be positive")
    if args.materialize_timeout_seconds <= 0:
        parser.error("--materialize-timeout-seconds must be positive")
    if args.materialize_poll_seconds <= 0:
        parser.error("--materialize-poll-seconds must be positive")
    if args.optimize_limit <= 0:
        parser.error("--optimize-limit must be positive")
    if args.log_every < 0:
        parser.error("--log-every must be non-negative")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    client = get_client(args)

    scanned_tables = 0
    skipped: list[SkippedTable] = []
    optimize_plans: list[OptimizePlan] = []
    if args.mode == "resume-materialize":
        log(args, "Resuming MATERIALIZE TTL state polling from system.mutations")
        plans = []
        batch = []
    elif args.mode == "optimize":
        log(args, f"Fetching largest active parts groups for OPTIMIZE; limit={args.optimize_limit}")
        plans = []
        batch = []
        optimize_plans = fetch_optimize_plans(client, args)
        log(args, f"Selected {len(optimize_plans)} optimize targets")
    else:
        stage_label = "MATERIALIZE TTL stage" if args.mode == "materialize" else "TTL RECOMPRESS planning"
        log(args, f"Fetching candidate MergeTree tables for {stage_label}")
        tables = fetch_tables(client, args)
        scanned_tables = len(tables)
        log(args, f"Fetched {scanned_tables} candidate tables")
        plans = []
        for index, table in enumerate(tables, start=1):
            if args.mode == "materialize":
                plan, reason = build_materialize_plan_for_table(table)
            else:
                plan, reason = build_plan_for_table(args, table)
            if plan:
                plans.append(plan)
            else:
                skipped.append(SkippedTable(table.database, table.name, reason or "unknown reason"))
            if args.log_every and (index == 1 or index % args.log_every == 0 or index == len(tables)):
                log(
                    args,
                    "Processed "
                    f"{index}/{len(tables)} tables; planned={len(plans)}, skipped={len(skipped)}, "
                    f"current={table.database}.{table.name}",
                )
        plans = sort_plans_by_database_size(plans)
        batch = select_batch(args, plans)
        if args.all_batches:
            log(args, f"Selected all batches: {len(batch)} tables")
        else:
            log(args, f"Selected batch {args.batch}: {len(batch)} tables")
        write_skip_report(args, skipped)
        log(args, f"Wrote skip report under {args.output_dir}")

    print(f"Mode: {args.mode}")
    print(f"Scanned tables: {scanned_tables}")
    print(f"Planned tables: {len(plans)}")
    print(f"Skipped tables: {len(skipped)}")
    print_processing_summary(plans)
    start = args.batch * args.batch_size
    end = start + args.batch_size
    if args.all_batches:
        print(f"Batch: all, size {len(batch)}")
    else:
        print(f"Batch: {args.batch} ({start}..{max(start, end - 1)}), size {len(batch)}")
    print(f"Output directory: {args.output_dir}")
    print()

    if args.mode == "optimize":
        print("Optimize targets by active bytes desc:")
        for index, plan in enumerate(optimize_plans, start=1):
            print(f"[{index}] {plan.database}.{plan.table}")
            print(f"    partition: {plan.partition}")
            print(f"    partition_id: {plan.partition_id}")
            print(f"    default_compression_codec: {plan.default_compression_codec}")
            print(f"    bytes: {plan.bytes} ({format_readable_size(plan.bytes)})")
            print("    planned OPTIMIZE statement:")
            print(f"      {plan.statement}")
            print()
    for index, plan in enumerate(batch, start=start + 1):
        print(f"[{index}] {plan.table.database}.{plan.table.name}")
        print(f"    partition_key: {plan.table.partition_key}")
        if args.mode == "materialize":
            print("    current TTL RECOMPRESS:")
            print_entries("      ", plan.current_ttl_recompress_entries)
            print("    MATERIALIZE plan:")
            print("      " + materialize_statement(args, plan))
        else:
            print("    current:")
            print(f"      table-level TTL: {plan.current_ttl_state}")
            print("      TTL RECOMPRESS:")
            print_entries("        ", plan.current_ttl_recompress_entries)
            print("      TTL DELETE:")
            print_entries("        ", plan.current_ttl_delete_entries)
            if plan.current_ttl_other_entries:
                print("      TTL other:")
                print_entries("        ", plan.current_ttl_other_entries)
            print("    planned:")
            print(f"      TTL RECOMPRESS: {plan.recompress_expr} RECOMPRESS CODEC({args.codec})")
            print("      full TTL:")
            print_entries("        ", plan.planned_ttl_entries)
            print("    planned replicated setting statement:")
            print("      " + recalculate_only_setting_statement(plan).replace("\n", "\n      "))
            print("    planned replicated TTL statement:")
            print("      " + ttl_statement(plan).replace("\n", "\n      "))
        print()

    if args.mode == "optimize":
        if optimize_plans:
            execute_optimize_plans(client, optimize_plans)
            print("Executed OPTIMIZE statements for selected largest parts groups.")
        else:
            print("No OPTIMIZE statements to execute.")
    elif args.mode == "apply-ttl":
        if batch:
            execute_ttl_batch(client, batch)
            print("Executed replicated setting and TTL ALTER statements for current batch.")
        else:
            print("No replicated setting or TTL ALTER statements to execute for current batch.")
        if not args.all_batches and len(plans) > end:
            print(
                "More planned tables remain. Re-run with "
                f"--batch {args.batch + 1} or use --all-batches to process all planned tables."
            )
    elif args.mode in {"materialize", "resume-materialize"}:
        states = execute_materialize_batch(client, args, batch)
        print("Materialize states:")
        for state in states:
            print(
                f"  {state.database}.{state.table}: {state.status}, "
                f"mutation_id={state.mutation_id}, parts_to_do={state.parts_to_do}, "
                f"latest_fail_reason={state.latest_fail_reason or '-'}"
            )
        if args.mode == "materialize" and not args.all_batches and len(plans) > end:
            print(
                "More materialize candidates remain. Re-run with "
                f"--batch {args.batch + 1} or use --all-batches to process all planned tables."
            )
    else:
        print("Dry-run only.")
        print("Run --mode apply-ttl once per `ReplicatedMergeTree` replica group.")
        print("After every table has been processed by --mode apply-ttl, run --mode optimize.")

    if skipped:
        print(f"Skipped table report: {Path(args.output_dir) / args.skip_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
