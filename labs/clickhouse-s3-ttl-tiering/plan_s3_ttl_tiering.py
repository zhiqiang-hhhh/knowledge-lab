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
MODES = {"plan", "apply-policy", "apply-ttl", "materialize", "resume-materialize"}


@dataclasses.dataclass
class TableInfo:
    database: str
    name: str
    engine: str
    partition_key: str
    create_table_query: str
    storage_policy: str
    total_rows: int
    total_bytes: int


@dataclasses.dataclass
class TablePlan:
    table: TableInfo
    move_expr: str
    current_ttl_move_entries: list[str]
    current_ttl_recompress_entries: list[str]
    current_ttl_delete_entries: list[str]
    current_ttl_other_entries: list[str]
    ttl_delete_entries: list[str]
    statements: list[str]


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


def quote_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def quote_table(database: str, table: str) -> str:
    return f"{quote_identifier(database)}.{quote_identifier(table)}"


def quote_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


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
    if "ttl" not in create_table_query.lower():
        return None, "missing table-level TTL"

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


def validate_delete_only_ttl(entries: list[str]) -> tuple[list[str] | None, str | None]:
    accepted = []
    for entry in entries:
        if re.search(r"\bTO\s+(?:VOLUME|DISK)\b", entry, flags=re.IGNORECASE):
            return None, f"existing TTL entry is a MOVE rule: {entry}"
        if re.search(r"\bRECOMPRESS\b", entry, flags=re.IGNORECASE):
            return None, f"existing TTL entry is a RECOMPRESS rule: {entry}"
        if re.search(r"\bGROUP\s+BY\b", entry, flags=re.IGNORECASE):
            return None, f"existing TTL entry is an aggregation rule: {entry}"
        if re.search(r"\bDELETE\s+WHERE\b", entry, flags=re.IGNORECASE):
            return None, f"existing TTL entry has DELETE WHERE: {entry}"
        accepted.append(entry)
    return accepted, None


def classify_ttl_entries(entries: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    move_entries = []
    recompress_entries = []
    delete_entries = []
    other_entries = []

    for entry in entries:
        if re.search(r"\bTO\s+(?:VOLUME|DISK)\b", entry, flags=re.IGNORECASE):
            move_entries.append(entry)
        elif re.search(r"\bRECOMPRESS\b", entry, flags=re.IGNORECASE):
            recompress_entries.append(entry)
        elif re.search(r"\bGROUP\s+BY\b|\bDELETE\s+WHERE\b", entry, flags=re.IGNORECASE):
            other_entries.append(entry)
        else:
            delete_entries.append(entry)

    return move_entries, recompress_entries, delete_entries, other_entries


def remove_existing_tiering_ttl_entries(
    args: argparse.Namespace,
    entries: list[str],
) -> tuple[list[str] | None, str | None]:
    kept = []
    removed_move = 0
    removed_recompress = 0
    volume_pattern = re.compile(
        rf"\bTO\s+VOLUME\s+(?:\\?'|\")?{re.escape(args.cold_volume)}(?:\\?'|\")?",
        flags=re.IGNORECASE,
    )
    recompress_pattern = re.compile(r"\bRECOMPRESS\s+CODEC\s*\(", flags=re.IGNORECASE)

    for entry in entries:
        if volume_pattern.search(entry):
            removed_move += 1
            continue
        if recompress_pattern.search(entry):
            removed_recompress += 1
            continue
        kept.append(entry)

    if not removed_move:
        return None, f"repair mode found no existing TTL MOVE to volume {args.cold_volume}"
    if not removed_recompress:
        return None, "repair mode found no existing TTL RECOMPRESS entry"
    return kept, None


def partition_key_kind(partition_key: str) -> str | None:
    if re.search(r"\b(?:toMonday|toStartOfWeek)\s*\(", partition_key, flags=re.IGNORECASE):
        return "week"
    if re.search(r"\b(?:toDate|toStartOfDay)\s*\(", partition_key, flags=re.IGNORECASE):
        return "day"
    return None


def infer_move_expr(args: argparse.Namespace, partition_key: str) -> tuple[str | None, str | None]:
    if args.time_column:
        return None, "--time-column is no longer supported; TTL MOVE uses partition_key directly"

    kind = partition_key_kind(partition_key)
    if kind == "week":
        return f"{partition_key} + INTERVAL {args.weekly_hot_weeks} WEEK", None
    if kind == "day":
        return f"{partition_key} + INTERVAL {args.daily_hot_days} DAY", None

    return None, f"unsupported Date-like partition key: {partition_key}"


def fetch_storage_policies(client) -> dict[str, set[str]]:
    rows = query_rows(
        client,
        """
        SELECT
            policy_name,
            volume_name
        FROM system.storage_policies
        """,
    )
    policies: dict[str, set[str]] = {}
    for row in rows:
        policies.setdefault(row["policy_name"], set()).add(row["volume_name"])
    return policies


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
            storage_policy,
            total_rows,
            total_bytes
        FROM system.tables
        WHERE {' AND '.join(where)}
        ORDER BY database, name
    """
    rows = query_rows(client, query)
    return [
        TableInfo(
            database=row["database"],
            name=row["name"],
            engine=row["engine"],
            partition_key=row.get("partition_key") or "",
            create_table_query=row.get("create_table_query") or "",
            storage_policy=row.get("storage_policy") or "default",
            total_rows=int(row.get("total_rows") or 0),
            total_bytes=int(row.get("total_bytes") or 0),
        )
        for row in rows
    ]


def build_plan_for_table(
    args: argparse.Namespace,
    policy_volumes: dict[str, set[str]],
    table: TableInfo,
) -> tuple[TablePlan | None, str | None]:
    if args.mode == "apply-ttl" and table.storage_policy != args.target_policy:
        return None, (
            f"apply-ttl requires current storage policy {args.target_policy}; "
            f"current policy is {table.storage_policy}. Run apply-policy for this replica group first "
            "and wait until this replica applies the metadata"
        )

    repair_existing_ttl = bool(args.repair_existing_tiering_ttl and table.storage_policy == args.target_policy)
    if args.repair_existing_tiering_ttl and table.storage_policy != args.target_policy:
        return None, (
            "repair mode only handles tables already using storage policy "
            f"{args.target_policy}; current policy is {table.storage_policy}"
        )
    if (
        table.storage_policy == args.target_policy
        and not (args.allow_already_policy or repair_existing_ttl or args.mode == "apply-ttl")
    ):
        return None, f"already uses storage policy {args.target_policy}"
    if table.storage_policy not in {"default", args.target_policy} and not args.allow_non_default_policy:
        return None, f"current storage policy is {table.storage_policy}, not default"
    if table.storage_policy != args.target_policy:
        current_volumes = policy_volumes.get(table.storage_policy, set())
        target_volumes = policy_volumes.get(args.target_policy, set())
        missing_volumes = sorted(current_volumes - target_volumes)
        if missing_volumes:
            return (
                None,
                "target storage policy is not compatible with current policy "
                f"{table.storage_policy}; missing volumes: {', '.join(missing_volumes)}",
            )

    ttl_entries, error = extract_table_ttl_entries(table.create_table_query)
    if error:
        return None, error

    (
        current_move_entries,
        current_recompress_entries,
        current_delete_entries,
        current_other_entries,
    ) = classify_ttl_entries(ttl_entries or [])

    if repair_existing_ttl:
        ttl_entries, error = remove_existing_tiering_ttl_entries(args, ttl_entries or [])
        if error:
            return None, error

    delete_entries, error = validate_delete_only_ttl(ttl_entries or [])
    if error:
        return None, error

    move_expr, error = infer_move_expr(args, table.partition_key)
    if error:
        return None, error

    full_ttl_entries = [
        f"{move_expr} TO VOLUME {quote_literal(args.cold_volume)}",
        f"{move_expr} RECOMPRESS CODEC({args.codec})",
        *(delete_entries or []),
    ]
    qtable = quote_table(table.database, table.name)
    statements = [
        f"ALTER TABLE {qtable} MODIFY SETTING storage_policy = {quote_literal(args.target_policy)}",
        "ALTER TABLE "
        + qtable
        + " MODIFY TTL\n    "
        + ",\n    ".join(full_ttl_entries)
        + "\nSETTINGS materialize_ttl_after_modify = 0",
    ]

    return (
        TablePlan(
            table=table,
            move_expr=move_expr or "",
            current_ttl_move_entries=current_move_entries,
            current_ttl_recompress_entries=current_recompress_entries,
            current_ttl_delete_entries=current_delete_entries,
            current_ttl_other_entries=current_other_entries,
            ttl_delete_entries=delete_entries or [],
            statements=statements,
        ),
        None,
    )


def build_materialize_plan_for_table(args: argparse.Namespace, table: TableInfo) -> tuple[TablePlan | None, str | None]:
    if table.storage_policy != args.target_policy:
        return None, f"current storage policy is {table.storage_policy}, not {args.target_policy}"
    create_query = table.create_table_query
    if not re.search(rf"\bTO\s+VOLUME\s+\\?'{re.escape(args.cold_volume)}\\?'", create_query, flags=re.IGNORECASE):
        return None, f"TTL does not contain MOVE to volume {args.cold_volume}"
    if not re.search(r"\bRECOMPRESS\b", create_query, flags=re.IGNORECASE):
        return None, "TTL does not contain RECOMPRESS"

    return (
        TablePlan(
            table=table,
            move_expr="existing TTL MOVE expression",
            current_ttl_move_entries=[],
            current_ttl_recompress_entries=[],
            current_ttl_delete_entries=[],
            current_ttl_other_entries=[],
            ttl_delete_entries=[],
            statements=[],
        ),
        None,
    )


def materialize_statement(args: argparse.Namespace, plan: TablePlan) -> str:
    return (
        f"ALTER TABLE {quote_table(plan.table.database, plan.table.name)} "
        f"MATERIALIZE TTL SETTINGS mutations_sync = {args.mutations_sync}"
    )


def policy_statement(plan: TablePlan) -> str:
    return plan.statements[0]


def ttl_statement(plan: TablePlan) -> str:
    return plan.statements[1]


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


def execute_policy_batch(client, batch: list[TablePlan]) -> None:
    for plan in batch:
        print(f"Applying storage_policy ALTER {plan.table.database}.{plan.table.name}", flush=True)
        command(client, policy_statement(plan))


def execute_ttl_batch(client, batch: list[TablePlan]) -> None:
    for plan in batch:
        print(f"Applying replicated TTL {plan.table.database}.{plan.table.name}", flush=True)
        command(client, ttl_statement(plan))


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
    command(client, statement)
    after = query_materialize_mutations(client, database, table)
    for state in after:
        if state.mutation_id not in before_ids:
            return state
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
            table,
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
            wait_for_materialize_submit_capacity(client, args)
            log(args, f"Submitting MATERIALIZE TTL {index}/{len(batch)}")
            states.append(submit_materialize(client, args, plan))
    if args.wait_materialize:
        log(args, f"Polling MATERIALIZE TTL state for up to {args.materialize_timeout_seconds} seconds")
        states = wait_for_materialize(client, args, states)
    return states


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan or execute ClickHouse TTL tiering ALTERs for S3 cold storage."
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
    parser.add_argument("--target-policy", default="s3_tier")
    parser.add_argument("--cold-volume", default="cold")
    parser.add_argument("--codec", default="ZSTD(12)")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--batch", type=int, default=0)
    parser.add_argument("--all-batches", action="store_true", help="Process all planned tables instead of only one batch.")
    parser.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="plan",
        help=(
            "Execution mode. plan is dry-run; apply-policy submits storage_policy metadata ALTER; "
            "apply-ttl submits replicated TTL metadata ALTER; materialize submits MATERIALIZE TTL; "
            "resume-materialize only watches existing MATERIALIZE TTL mutations."
        ),
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute-alter", action="store_true", help=argparse.SUPPRESS)
    action.add_argument("--execute-materialize", action="store_true", help=argparse.SUPPRESS)
    action.add_argument("--resume-materialize", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", default=".", help="Directory for run log and skip report.")
    parser.add_argument("--log-file", default="s3_ttl_tiering.log")
    parser.add_argument("--skip-report", default="s3_ttl_tiering_skipped.tsv")
    parser.add_argument(
        "--time-column",
        help="Deprecated; rejected because TTL MOVE now uses partition_key directly.",
    )
    parser.add_argument("--weekly-hot-weeks", type=int, default=2)
    parser.add_argument("--daily-hot-days", type=int, default=8)
    parser.add_argument("--mutations-sync", type=int, default=1)
    parser.add_argument("--wait-materialize", action="store_true")
    parser.add_argument(
        "--max-pending-materialize",
        type=int,
        default=1,
        help="Maximum pending MATERIALIZE TTL mutations before submitting the next table.",
    )
    parser.add_argument("--materialize-timeout-seconds", type=int, default=3600)
    parser.add_argument("--materialize-poll-seconds", type=float, default=5.0)
    parser.add_argument("--log-every", type=int, default=100, help="Print scan progress every N tables. Use 0 to disable.")
    parser.add_argument("--quiet", action="store_true", help="Disable progress logs.")
    parser.add_argument("--allow-already-policy", action="store_true")
    parser.add_argument("--allow-non-default-policy", action="store_true")
    parser.add_argument(
        "--repair-existing-tiering-ttl",
        action="store_true",
        help=(
            "For tables already using target policy, remove existing TTL MOVE/RECOMPRESS "
            "entries for the cold tier and rebuild them from partition_key while preserving DELETE TTL."
        ),
    )
    args = parser.parse_args(argv)
    mode_explicit = "--mode" in argv or any(item.startswith("--mode=") for item in argv)
    if args.execute_alter:
        parser.error(
            "--execute-alter is deprecated and unsafe for ReplicatedMergeTree; "
            "run --mode apply-policy once per replica group, wait for metadata alignment, "
            "then run --mode apply-ttl once per replica group"
        )
    if args.execute_materialize:
        if mode_explicit and args.mode != "materialize":
            parser.error("--execute-materialize conflicts with --mode; use --mode materialize")
        args.mode = "materialize"
    if args.resume_materialize:
        if mode_explicit and args.mode != "resume-materialize":
            parser.error("--resume-materialize conflicts with --mode; use --mode resume-materialize")
        args.mode = "resume-materialize"

    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    if args.batch < 0:
        parser.error("--batch must be non-negative")
    if args.weekly_hot_weeks < 2:
        parser.error("--weekly-hot-weeks must be at least 2 to keep last Sunday hot on Monday")
    if args.daily_hot_days < 7:
        parser.error("--daily-hot-days must be at least 7")
    if args.mutations_sync not in {0, 1, 2}:
        parser.error("--mutations-sync must be 0, 1, or 2")
    if args.max_pending_materialize <= 0:
        parser.error("--max-pending-materialize must be positive")
    if args.materialize_timeout_seconds <= 0:
        parser.error("--materialize-timeout-seconds must be positive")
    if args.materialize_poll_seconds <= 0:
        parser.error("--materialize-poll-seconds must be positive")
    if args.log_every < 0:
        parser.error("--log-every must be non-negative")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    client = get_client(args)

    scanned_tables = 0
    skipped: list[SkippedTable] = []
    if args.mode == "resume-materialize":
        log(args, "Resuming MATERIALIZE TTL state polling from system.mutations")
        plans = []
        batch = []
    elif args.mode == "materialize":
        log(args, "Fetching candidate MergeTree tables for MATERIALIZE TTL stage")
        tables = fetch_tables(client, args)
        scanned_tables = len(tables)
        plans = []
        for index, table in enumerate(tables, start=1):
            plan, reason = build_materialize_plan_for_table(args, table)
            if plan:
                plans.append(plan)
            else:
                skipped.append(SkippedTable(table.database, table.name, reason or "unknown reason"))
            if args.log_every and (index == 1 or index % args.log_every == 0 or index == len(tables)):
                log(
                    args,
                    "Processed "
                    f"{index}/{len(tables)} tables for materialize; planned={len(plans)}, skipped={len(skipped)}, "
                    f"current={table.database}.{table.name}",
                )
        plans = sort_plans_by_database_size(plans)
        batch = select_batch(args, plans)
        if args.all_batches:
            log(args, f"Selected all materialize batches: {len(batch)} tables")
        else:
            log(args, f"Selected materialize batch {args.batch}: {len(batch)} tables")
        write_skip_report(args, skipped)
        log(args, f"Wrote materialize skip report under {args.output_dir}")
    else:
        log(args, "Fetching storage policy metadata")
        policies = fetch_storage_policies(client)
        if args.target_policy not in policies:
            raise RuntimeError(f"storage policy {args.target_policy!r} is not present in system.storage_policies")
        if args.cold_volume not in policies[args.target_policy]:
            raise RuntimeError(
                f"storage policy {args.target_policy!r} does not contain volume {args.cold_volume!r}"
            )
        log(args, "Fetching candidate MergeTree tables from system.tables")
        tables = fetch_tables(client, args)
        scanned_tables = len(tables)
        log(args, f"Fetched {scanned_tables} candidate tables")
        plans = []
        for index, table in enumerate(tables, start=1):
            plan, reason = build_plan_for_table(args, policies, table)
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

    for index, plan in enumerate(batch, start=start + 1):
        print(f"[{index}] {plan.table.database}.{plan.table.name}")
        print(f"    partition_key: {plan.table.partition_key}")
        if args.mode == "materialize":
            print("    MATERIALIZE plan:")
            print("      " + materialize_statement(args, plan))
        else:
            print("    current:")
            print(f"      storage_policy: {plan.table.storage_policy}")
            print("      TTL MOVE:")
            print_entries("        ", plan.current_ttl_move_entries)
            print("      TTL RECOMPRESS:")
            print_entries("        ", plan.current_ttl_recompress_entries)
            print("      TTL DELETE:")
            print_entries("        ", plan.current_ttl_delete_entries)
            if plan.current_ttl_other_entries:
                print("      TTL other:")
                print_entries("        ", plan.current_ttl_other_entries)
            print("    planned:")
            print(f"      storage_policy: {args.target_policy}")
            print(f"      TTL MOVE: {plan.move_expr} TO VOLUME {quote_literal(args.cold_volume)}")
            print(f"      TTL RECOMPRESS: {plan.move_expr} RECOMPRESS CODEC({args.codec})")
            print("      TTL DELETE:")
            print_entries("        ", plan.ttl_delete_entries)
            print("    planned statements:")
            print("      local policy:")
            print("        " + policy_statement(plan))
            print("      replicated TTL:")
            print("        " + ttl_statement(plan).replace("\n", "\n        "))
        print()

    if args.mode == "apply-policy":
        if batch:
            execute_policy_batch(client, batch)
            print("Executed storage_policy ALTER statements for current batch.")
        else:
            print("No storage_policy ALTER statements to execute for current batch.")
        if not args.all_batches and len(plans) > end:
            print(
                "More planned tables remain. Re-run with "
                f"--batch {args.batch + 1} or use --all-batches to process all planned tables."
            )
    elif args.mode == "apply-ttl":
        if batch:
            execute_ttl_batch(client, batch)
            print("Executed replicated TTL ALTER statements for current batch.")
        else:
            print("No replicated TTL ALTER statements to execute for current batch.")
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
        print("Run --mode apply-policy once per replica group, then --mode apply-ttl once per replica group.")
        print("Use --mode materialize only after TTL ALTER has been reviewed/applied and replica metadata is aligned.")

    if skipped:
        print(f"Skipped table report: {Path(args.output_dir) / args.skip_report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
