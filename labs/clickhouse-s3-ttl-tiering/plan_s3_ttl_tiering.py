#!/usr/bin/env python3
import argparse
import dataclasses
import json
import re
import sys
import time
from pathlib import Path

try:
    import clickhouse_connect
except ModuleNotFoundError:
    clickhouse_connect = None


SYSTEM_DATABASES = {"system", "INFORMATION_SCHEMA", "information_schema"}


@dataclasses.dataclass
class TableInfo:
    database: str
    name: str
    engine: str
    partition_key: str
    create_table_query: str
    storage_policy: str


@dataclasses.dataclass
class TablePlan:
    table: TableInfo
    move_expr: str
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
    if not getattr(args, "quiet", False):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] {message}", file=sys.stderr, flush=True)


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


def extract_single_argument(function_name: str, expression: str) -> str | None:
    pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(", flags=re.IGNORECASE)
    match = pattern.search(expression)
    if not match:
        return None

    start = match.end()
    depth = 1
    quote = None
    i = start
    while i < len(expression):
        ch = expression[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
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
                return expression[start:i].strip()
        i += 1
    return None


def infer_move_expr(args: argparse.Namespace, partition_key: str) -> tuple[str | None, str | None]:
    if args.time_column:
        time_expr = quote_identifier(args.time_column)
    else:
        time_expr = None

    weekly_arg = (
        extract_single_argument("toStartOfWeek", partition_key)
        or extract_single_argument("toMonday", partition_key)
    )
    if weekly_arg:
        time_expr = time_expr or weekly_arg
        return f"toStartOfWeek({time_expr}) + INTERVAL {args.weekly_hot_weeks} WEEK", None

    daily_arg = (
        extract_single_argument("toDate", partition_key)
        or extract_single_argument("toStartOfDay", partition_key)
        or extract_single_argument("toYYYYMMDD", partition_key)
    )
    if daily_arg:
        time_expr = time_expr or daily_arg
        return f"toDate({time_expr}) + INTERVAL {args.daily_hot_days} DAY", None

    return None, f"unsupported partition key: {partition_key}"


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

    query = f"""
        SELECT
            database,
            name,
            engine,
            partition_key,
            create_table_query,
            storage_policy
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
        )
        for row in rows
    ]


def build_plan_for_table(
    args: argparse.Namespace,
    policy_volumes: dict[str, set[str]],
    table: TableInfo,
) -> tuple[TablePlan | None, str | None]:
    if table.storage_policy == args.target_policy and not args.allow_already_policy:
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
            ttl_delete_entries=delete_entries or [],
            statements=statements,
        ),
        None,
    )


def materialize_statement(args: argparse.Namespace, plan: TablePlan) -> str:
    return (
        f"ALTER TABLE {quote_table(plan.table.database, plan.table.name)} "
        f"MATERIALIZE TTL SETTINGS mutations_sync = {args.mutations_sync}"
    )


def write_outputs(args: argparse.Namespace, plans: list[TablePlan], skipped: list[SkippedTable], batch: list[TablePlan]) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plan_sql = output_dir / f"s3_ttl_tiering_batch_{args.batch}.sql"
    plan_sql.write_text(
        "\n\n".join(";\n".join(plan.statements) + ";" for plan in batch) + ("\n" if batch else ""),
        encoding="utf-8",
    )

    skipped_tsv = output_dir / "s3_ttl_tiering_skipped.tsv"
    skipped_tsv.write_text(
        "database\ttable\treason\n"
        + "".join(f"{item.database}\t{item.table}\t{item.reason}\n" for item in skipped),
        encoding="utf-8",
    )

    all_plans_json = output_dir / "s3_ttl_tiering_plans.jsonl"
    all_plans_json.write_text(
        "".join(
            json.dumps(
                {
                    "database": plan.table.database,
                    "table": plan.table.name,
                    "partition_key": plan.table.partition_key,
                    "move_expr": plan.move_expr,
                    "ttl_delete_entries": plan.ttl_delete_entries,
                    "statements": plan.statements,
                    "materialize_statement": materialize_statement(args, plan),
                },
                ensure_ascii=False,
            )
            + "\n"
            for plan in plans
        ),
        encoding="utf-8",
    )

    if args.write_materialize_sql:
        materialize_sql = output_dir / f"s3_ttl_tiering_materialize_batch_{args.batch}.sql"
        materialize_sql.write_text(
            "\n".join(materialize_statement(args, plan) + ";" for plan in batch) + ("\n" if batch else ""),
            encoding="utf-8",
        )


def load_saved_plans(args: argparse.Namespace) -> list[TablePlan]:
    path = Path(args.output_dir) / "s3_ttl_tiering_plans.jsonl"
    if not path.exists():
        raise RuntimeError(f"plan file does not exist: {path}; run plan/alter stage first")
    plans = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        table = TableInfo(
            database=row["database"],
            name=row["table"],
            engine="",
            partition_key=row.get("partition_key", ""),
            create_table_query="",
            storage_policy=args.target_policy,
        )
        plans.append(
            TablePlan(
                table=table,
                move_expr=row.get("move_expr", ""),
                ttl_delete_entries=row.get("ttl_delete_entries", []),
                statements=row.get("statements", []),
            )
        )
    return plans


def select_batch(args: argparse.Namespace, plans: list[TablePlan]) -> list[TablePlan]:
    start = args.batch * args.batch_size
    end = start + args.batch_size
    return plans[start:end]


def execute_alter_batch(client, batch: list[TablePlan]) -> None:
    for plan in batch:
        print(f"Executing {plan.table.database}.{plan.table.name}", flush=True)
        for statement in plan.statements:
            command(client, statement)


def mutation_state_path(args: argparse.Namespace) -> Path:
    return Path(args.output_dir) / f"s3_ttl_tiering_materialize_state_batch_{args.batch}.jsonl"


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


def write_mutation_states(args: argparse.Namespace, states: list[MutationState]) -> None:
    output = mutation_state_path(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(dataclasses.asdict(state), ensure_ascii=False) + "\n" for state in states),
        encoding="utf-8",
    )


def read_mutation_states(args: argparse.Namespace) -> list[MutationState]:
    path = mutation_state_path(args)
    if not path.exists():
        raise RuntimeError(f"mutation state file does not exist: {path}")
    states = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            states.append(MutationState(**json.loads(line)))
    return states


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
        write_mutation_states(args, current)
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


def execute_materialize_batch(client, args: argparse.Namespace, batch: list[TablePlan]) -> list[MutationState]:
    if args.resume_materialize:
        log(args, "Reading saved MATERIALIZE TTL mutation state")
        states = read_mutation_states(args)
    else:
        log(args, f"Submitting MATERIALIZE TTL for {len(batch)} tables")
        states = [submit_materialize(client, args, plan) for plan in batch]
    write_mutation_states(args, states)
    if args.wait_materialize:
        log(args, f"Polling MATERIALIZE TTL state for up to {args.materialize_timeout_seconds} seconds")
        states = wait_for_materialize(client, args, states)
        write_mutation_states(args, states)
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
    parser.add_argument("--target-policy", default="s3_tier")
    parser.add_argument("--cold-volume", default="cold")
    parser.add_argument("--codec", default="ZSTD(12)")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--batch", type=int, default=0)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute-alter", action="store_true")
    action.add_argument("--execute-materialize", action="store_true")
    action.add_argument("--resume-materialize", action="store_true")
    parser.add_argument("--output-dir", default="tmp")
    parser.add_argument("--write-materialize-sql", action="store_true")
    parser.add_argument("--time-column", help="Override inferred time expression with this column name.")
    parser.add_argument("--weekly-hot-weeks", type=int, default=2)
    parser.add_argument("--daily-hot-days", type=int, default=8)
    parser.add_argument("--mutations-sync", type=int, default=0)
    parser.add_argument("--wait-materialize", action="store_true")
    parser.add_argument("--materialize-timeout-seconds", type=int, default=3600)
    parser.add_argument("--materialize-poll-seconds", type=float, default=5.0)
    parser.add_argument("--log-every", type=int, default=100, help="Print scan progress every N tables. Use 0 to disable.")
    parser.add_argument("--quiet", action="store_true", help="Disable progress logs.")
    parser.add_argument("--allow-already-policy", action="store_true")
    parser.add_argument("--allow-non-default-policy", action="store_true")
    args = parser.parse_args(argv)
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
    if args.resume_materialize:
        log(args, "Resuming MATERIALIZE TTL state polling from saved state file")
        plans = []
        batch = []
    elif args.execute_materialize:
        log(args, "Loading saved table plan for MATERIALIZE TTL stage")
        plans = load_saved_plans(args)
        batch = select_batch(args, plans)
        scanned_tables = len(plans)
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
        batch = select_batch(args, plans)
        log(args, f"Selected batch {args.batch}: {len(batch)} tables")
        write_outputs(args, plans, skipped, batch)
        log(args, f"Wrote plan outputs under {args.output_dir}")

    print(f"Scanned tables: {scanned_tables}")
    print(f"Planned tables: {len(plans)}")
    print(f"Skipped tables: {len(skipped)}")
    start = args.batch * args.batch_size
    end = start + args.batch_size
    print(f"Batch: {args.batch} ({start}..{max(start, end - 1)}), size {len(batch)}")
    print(f"Output directory: {args.output_dir}")
    print()

    for index, plan in enumerate(batch, start=start + 1):
        print(f"[{index}] {plan.table.database}.{plan.table.name}")
        print(f"    partition_key: {plan.table.partition_key}")
        print(f"    move/recompress: {plan.move_expr}")
        print("    ALTER plan:")
        for statement in plan.statements:
            print("      " + statement.replace("\n", "\n      "))
        print()

    if args.execute_alter:
        execute_alter_batch(client, batch)
        print("Executed ALTER statements for current batch.")
    elif args.execute_materialize or args.resume_materialize:
        states = execute_materialize_batch(client, args, batch)
        print("Materialize states:")
        for state in states:
            print(
                f"  {state.database}.{state.table}: {state.status}, "
                f"mutation_id={state.mutation_id}, parts_to_do={state.parts_to_do}, "
                f"latest_fail_reason={state.latest_fail_reason or '-'}"
            )
    else:
        print("Dry-run only. Re-run with --execute-alter to apply ALTER statements for the current batch.")
        print("Use --execute-materialize only after ALTER has been reviewed/applied.")

    if skipped:
        print(f"Skipped table report: {Path(args.output_dir) / 's3_ttl_tiering_skipped.tsv'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
