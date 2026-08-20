#!/usr/bin/env python3
"""Plan or apply a TTL RECOMPRESS rule to ClickHouse MergeTree tables."""

from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
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
DEFAULT_SKIPPED_SUMMARY_LIMIT = 20
DEFAULT_SKIPPED_SUMMARY_SCAN_LIMIT = 1000
REQUIRED_TABLE_SETTINGS = {
    "materialize_ttl_recalculate_only": {"1", "true"},
}
_APPLY_THREAD_LOCAL = threading.local()


@dataclass(frozen=True)
class Table:
    database: str
    name: str
    create_query: str
    partition_key: str
    total_rows: int
    total_bytes: int
    local_bytes: int = 0
    remote_bytes: int = 0
    storage_policy: str = "default"


@dataclass(frozen=True)
class RankedTable:
    database: str
    name: str
    total_rows: int
    total_bytes: int
    local_bytes: int = 0
    remote_bytes: int = 0


@dataclass(frozen=True)
class PlannedTable:
    table: Table
    ttl: str | None
    ttl_base: str | None
    reason: str | None


@dataclass(frozen=True)
class RepairSettingPlan:
    tables: list[Table]
    recompress_tables: list[Table]
    repair_tables: list[Table]


@dataclass(frozen=True)
class StorageTopology:
    remote_disks: frozenset[str]
    volume_disks: dict[tuple[str, str], tuple[str, ...]]


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


def ttl_move_targets(ttl: str | None) -> list[tuple[str, str]]:
    if not ttl:
        return []
    pattern = re.compile(
        r"\bTO\s+(VOLUME|DISK)\s+(?:'((?:\\.|[^'])*)'|\"((?:\\.|[^\"])*)\"|`([^`]+)`|([A-Za-z_][A-Za-z0-9_]*))",
        re.IGNORECASE,
    )
    targets: list[tuple[str, str]] = []
    for match in pattern.finditer(ttl):
        value = next(group for group in match.groups()[1:] if group is not None)
        targets.append((match.group(1).lower(), value))
    return targets


def has_ttl_delete(ttl: str) -> bool:
    for rule in split_top_level_csv(ttl):
        if re.search(r"\bDELETE\b", rule, re.IGNORECASE):
            return True
        if not re.search(r"\bTO\s+(?:VOLUME|DISK)\b|\bRECOMPRESS\b|\bGROUP\s+BY\b", rule, re.IGNORECASE):
            return True
    return False


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


def split_top_level_csv(value: str) -> list[str]:
    items: list[str] = []
    depth = 0
    quote = ""
    start = 0
    for index, char in enumerate(value):
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
            item = value[start:index].strip()
            if item:
                items.append(item)
            start = index + 1
    item = value[start:].strip()
    if item:
        items.append(item)
    return items


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
    for item in split_top_level_csv(body):
        line = item.strip()
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


def expression_references_column(expression: str, column: str) -> bool:
    escaped = re.escape(column)
    return re.search(rf"(?<![A-Za-z0-9_`])`?{escaped}`?(?![A-Za-z0-9_`])", expression) is not None


def expression_references_datetime64(expression: str, column_types: dict[str, str]) -> bool:
    return any(
        is_datetime64_type(column_type) and expression_references_column(expression, column)
        for column, column_type in column_types.items()
    )


def ttl_compatible_expression(expression: str, column_types: dict[str, str]) -> str:
    value = expression.strip()
    call = split_function_call(value)
    if call is not None:
        function, arguments = call
        normalized = function.lower()
        first_argument = first_function_argument(arguments)
        if normalized == "todatetime64":
            return f"toDateTime({value})"
        if expression_references_datetime64(arguments, column_types):
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


def normalize_setting_value(value: str) -> str:
    value = value.strip().rstrip(";")
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        value = value[1:-1]
    return value.strip().lower()


def extract_table_settings(create_query: str) -> dict[str, str]:
    settings = find_keyword(create_query, "SETTINGS")
    if settings < 0:
        return {}
    body = create_query[settings + len("SETTINGS") :].strip()
    parsed: dict[str, str] = {}
    for item in split_top_level_csv(body):
        match = re.match(r"`?([A-Za-z_][A-Za-z0-9_]*)`?\s*=\s*(.+)$", item.strip())
        if not match:
            continue
        parsed[match.group(1).lower()] = normalize_setting_value(match.group(2))
    return parsed


def required_table_settings_satisfied(create_query: str) -> bool:
    settings = extract_table_settings(create_query)
    return all(settings.get(name) in values for name, values in REQUIRED_TABLE_SETTINGS.items())


def materialize_ttl_recalculate_only_enabled(create_query: str) -> bool:
    return extract_table_settings(create_query).get("materialize_ttl_recalculate_only") in {"1", "true"}


def should_materialize_ttl_after_modify(ttl: str | None, configured: bool) -> bool:
    """Never auto-materialize a modified TTL for tables with MOVE rules."""
    return configured and not (ttl and has_ttl_move(ttl))


def render_alters(
    table: Table,
    ttl: str | None,
    ttl_base: str,
    codec: str,
    cluster: str | None,
    materialize_ttl_after_modify: bool,
) -> list[str]:
    on_cluster = f" ON CLUSTER {quote_ident(cluster)}" if cluster else ""
    recompress_interval = "1 DAY" if ttl and has_ttl_move(ttl) else "1 WEEK"
    new_rule = f"{ttl_base} + INTERVAL {recompress_interval} RECOMPRESS CODEC({codec})"
    full_ttl = f"{ttl}, {new_rule}" if ttl else new_rule
    ttl_statement = f"ALTER TABLE {qualified(table)}{on_cluster} MODIFY TTL {full_ttl}"
    if not should_materialize_ttl_after_modify(ttl, materialize_ttl_after_modify):
        ttl_statement += "\nSETTINGS materialize_ttl_after_modify = 0"
    statements = []
    if not required_table_settings_satisfied(table.create_query):
        statements.append(
            f"ALTER TABLE {qualified(table)}{on_cluster} MODIFY SETTING "
            "materialize_ttl_recalculate_only = true"
        )
    statements.append(ttl_statement)
    return statements


def csv_values(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(frozen=True)
class ClusterNode:
    host: str
    port: int | None = None


@dataclass(frozen=True)
class Cluster:
    name: str
    nodes: tuple[ClusterNode, ...]


def parse_cluster_node(value: str, default_port: int | None) -> ClusterNode:
    """Parse a ``host`` or ``host:port`` node entry."""
    value = value.strip()
    if value.startswith("[") and "]" in value:  # bracketed IPv6, optional :port
        host, _, rest = value[1:].partition("]")
        port = rest.lstrip(":")
        return ClusterNode(host, int(port) if port else default_port)
    host, sep, port = value.rpartition(":")
    if sep and port.isdigit():
        return ClusterNode(host, int(port))
    return ClusterNode(value, default_port)


def parse_cluster_file(path: str, default_port: int | None = None) -> Cluster:
    """Parse one pssh-style cluster file: one node per line, the file name (without
    its extension) is the cluster name. Blank lines and ``#`` comments are ignored.

    Example ``perf-CH1-arm.txt``::

        10.21.5.164
        10.21.5.44
    """
    nodes: list[ClusterNode] = []
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            nodes.append(parse_cluster_node(line, default_port))
    name = os.path.splitext(os.path.basename(path))[0]
    return Cluster(name, tuple(nodes))


def load_clusters_dir(path: str, default_port: int | None = None) -> list[Cluster]:
    """Load clusters from ``path``. If ``path`` is a single file, it is one cluster;
    otherwise every ``*.txt`` file under the directory is a cluster keyed by file name."""
    if os.path.isfile(path):
        cluster = parse_cluster_file(path, default_port)
        if not cluster.nodes:
            raise ValueError(f"no nodes found in {path}")
        return [cluster]
    entries = sorted(
        entry.path
        for entry in os.scandir(path)
        if entry.is_file() and entry.name.endswith(".txt")
    )
    clusters = [
        cluster
        for entry in entries
        if (cluster := parse_cluster_file(entry, default_port)).nodes
    ]
    if not clusters:
        raise ValueError(f"no non-empty *.txt cluster files found in {path}")
    return clusters


def create_client(args: argparse.Namespace):
    return clickhouse_connect.get_client(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        secure=args.secure,
    )


def create_node_client(args: argparse.Namespace, node: ClusterNode):
    return clickhouse_connect.get_client(
        host=node.host,
        port=node.port if node.port is not None else args.port,
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
    conditions = ["p.active"]
    databases = csv_values(args.databases)
    if databases:
        conditions.append("p.database IN (" + ", ".join(map(quote_literal, databases)) + ")")
    elif not getattr(args, "include_system", False):
        conditions.append("p.database NOT IN (" + ", ".join(map(quote_literal, sorted(SYSTEM_DATABASES))) + ")")
    tables = csv_values(args.tables)
    if tables:
        conditions.append("p.`table` IN (" + ", ".join(map(quote_literal, tables)) + ")")
    limit_clause = "" if args.all else f"\n        LIMIT {args.limit}"
    query = (
        """
        SELECT
            p.database,
            p.`table`,
            sum(p.rows) AS total_rows,
            sum(p.bytes) AS total_bytes,
            sumIf(p.bytes, d.is_remote = 0) AS local_bytes,
            sumIf(p.bytes, d.is_remote = 1) AS remote_bytes
        FROM system.parts AS p
        LEFT JOIN system.disks AS d ON p.disk_name = d.name
        WHERE """
        + " AND ".join(conditions)
        + f"""
        GROUP BY p.database, p.`table`
        ORDER BY total_bytes DESC"""
        + limit_clause
        + """
        """
    )
    query = textwrap.dedent(query).strip()
    log_sql("fetch_parts", query)
    result = client.query(query)
    return [
        RankedTable(
            str(row[0]),
            str(row[1]),
            int(row[2]),
            int(row[3]),
            int(row[4]) if len(row) > 4 else int(row[3]),
            int(row[5]) if len(row) > 5 else 0,
        )
        for row in result.result_rows
    ]


def chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def fetch_metadata_batch(
    client,
    database: str,
    names: list[str],
    include_system: bool = False,
    log_query: bool = False,
) -> dict[tuple[str, str], tuple[str, str, str]]:
    system_filter = ""
    if not include_system:
        system_filter = (
            """
          AND database NOT IN ("""
            + ", ".join(map(quote_literal, sorted(SYSTEM_DATABASES)))
            + """)"""
        )
    query = (
        """
        SELECT
            database,
            name,
            create_table_query,
            partition_key,
            storage_policy
        FROM system.tables
        WHERE database = """
        + quote_literal(database)
        + """
          AND name IN ("""
        + ", ".join(map(quote_literal, names))
        + """)
        """
        + system_filter
        + """
          AND engine LIKE '%MergeTree%'
        """
    )
    query = textwrap.dedent(query).strip()
    if log_query:
        log_sql("fetch_metadata", query)
    result = client.query(query)
    return {
        (str(row[0]), str(row[1])): (
            str(row[2]),
            str(row[3]),
            str(row[4]) if len(row) > 4 else "default",
        )
        for row in result.result_rows
    }


def fetch_table_metadata(
    client,
    ranked: list[RankedTable],
    batch_size: int,
    include_system: bool = False,
) -> dict[tuple[str, str], tuple[str, str, str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for table in ranked:
        grouped[table.database].append(table.name)

    metadata: dict[tuple[str, str], tuple[str, str, str]] = {}
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
                    include_system=include_system,
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
    metadata = fetch_table_metadata(
        client,
        ranked,
        args.metadata_batch_size,
        include_system=getattr(args, "include_system", False),
    )
    tables: list[Table] = []
    for index, table in enumerate(ranked, start=1):
        name = f"{table.database}.{table.name}"
        details = metadata.get((table.database, table.name))
        if details is None:
            log(f"stage=fetch_metadata status=skipped table={index}/{len(ranked)} name={name} reason=not MergeTree or missing metadata")
            continue
        create_query, partition_key, storage_policy = details
        tables.append(
            Table(
                table.database,
                table.name,
                create_query,
                partition_key,
                table.total_rows,
                table.total_bytes,
                table.local_bytes,
                table.remote_bytes,
                storage_policy,
            )
        )
    return tables


def fetch_storage_topology(client) -> StorageTopology:
    disks_query = "SELECT name, is_remote FROM system.disks"
    policies_query = "SELECT policy_name, volume_name, disks FROM system.storage_policies"
    log_sql("fetch_storage_topology", disks_query)
    disk_rows = client.query(disks_query).result_rows
    log_sql("fetch_storage_topology", policies_query)
    policy_rows = client.query(policies_query).result_rows
    return StorageTopology(
        remote_disks=frozenset(str(row[0]) for row in disk_rows if int(row[1]) == 1),
        volume_disks={
            (str(row[0]), str(row[1])): tuple(str(disk) for disk in row[2])
            for row in policy_rows
        },
    )


def fetch_repair_setting_tables(client, args: argparse.Namespace) -> list[Table]:
    conditions = ["engine LIKE '%MergeTree%'"]
    databases = csv_values(args.databases)
    if databases:
        conditions.append("database IN (" + ", ".join(map(quote_literal, databases)) + ")")
    else:
        conditions.append("database NOT IN (" + ", ".join(map(quote_literal, sorted(SYSTEM_DATABASES))) + ")")
    tables = csv_values(args.tables)
    if tables:
        conditions.append("name IN (" + ", ".join(map(quote_literal, tables)) + ")")
    query = textwrap.dedent(
        f"""
        SELECT
            database,
            name
        FROM system.tables
        WHERE {' AND '.join(conditions)}
        ORDER BY database, name
        """
    ).strip()
    log_sql("fetch_repair_setting", query)
    result = client.query(query)
    ranked = [RankedTable(str(row[0]), str(row[1]), 0, 0) for row in result.result_rows]
    log(
        "stage=fetch_repair_setting_metadata status=started "
        f"tables={len(ranked)} batch_size={args.metadata_batch_size}"
    )
    metadata = fetch_table_metadata(
        client,
        ranked,
        args.metadata_batch_size,
        include_system=True,
    )
    log(f"stage=fetch_repair_setting_metadata status=completed tables={len(metadata)}")
    return [
        Table(table.database, table.name, details[0], details[1], 0, 0)
        for table in ranked
        if (details := metadata.get((table.database, table.name))) is not None
    ]


def plan_repair_settings(tables: list[Table]) -> RepairSettingPlan:
    recompress_tables = [
        table
        for table in tables
        if (ttl := extract_ttl(table.create_query)) is not None and has_recompress(ttl)
    ]
    repair_tables = [
        table
        for table in recompress_tables
        if not materialize_ttl_recalculate_only_enabled(table.create_query)
    ]
    return RepairSettingPlan(tables, recompress_tables, repair_tables)


def render_repair_setting_alter(table: Table, cluster: str | None) -> str:
    on_cluster = f" ON CLUSTER {quote_ident(cluster)}" if cluster else ""
    return (
        f"ALTER TABLE {qualified(table)}{on_cluster} "
        "MODIFY SETTING materialize_ttl_recalculate_only = true"
    )


def print_repair_setting_analysis(plan: RepairSettingPlan, cluster: str | None) -> None:
    satisfied = len(plan.recompress_tables) - len(plan.repair_tables)
    print("Repair-setting analysis:")
    print(f"  scanned MergeTree tables: {len(plan.tables)}")
    print(f"  tables with TTL RECOMPRESS: {len(plan.recompress_tables)}")
    print(f"  repair needed: {len(plan.repair_tables)}")
    print(f"  already enabled: {satisfied}")
    print()
    for index, table in enumerate(plan.repair_tables, start=1):
        print(f"-- repair-setting [{index}] {table.database}.{table.name}")
        print(render_repair_setting_alter(table, cluster) + ";")
        print()


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


def summarize_planned_tables(planned_tables: list[PlannedTable]) -> dict[str, int]:
    eligible = [planned for planned in planned_tables if planned.reason is None]
    skipped = [planned for planned in planned_tables if planned.reason is not None]
    return {
        "selected_tables": len(planned_tables),
        "eligible_tables": len(eligible),
        "skipped_tables": len(skipped),
        "selected_rows": sum(planned.table.total_rows for planned in planned_tables),
        "eligible_rows": sum(planned.table.total_rows for planned in eligible),
        "skipped_rows": sum(planned.table.total_rows for planned in skipped),
        "selected_bytes": sum(planned.table.total_bytes for planned in planned_tables),
        "eligible_bytes": sum(planned.table.total_bytes for planned in eligible),
        "skipped_bytes": sum(planned.table.total_bytes for planned in skipped),
        "eligible_local_bytes": sum(planned.table.local_bytes for planned in eligible),
        "eligible_remote_bytes": sum(planned.table.remote_bytes for planned in eligible),
    }


def classify_ttl_storage(planned: PlannedTable, topology: StorageTopology) -> str:
    targets = ttl_move_targets(planned.ttl)
    if not targets:
        return "local-only"
    resolved_disks: list[str] = []
    unresolved = False
    for kind, target in targets:
        if kind == "disk":
            resolved_disks.append(target)
            unresolved |= target not in topology.remote_disks and not any(
                target in disks for disks in topology.volume_disks.values()
            )
            continue
        disks = topology.volume_disks.get((planned.table.storage_policy, target))
        if disks is None:
            unresolved = True
        else:
            resolved_disks.extend(disks)
    if any(disk in topology.remote_disks for disk in resolved_disks):
        return "s3-remote-move"
    if unresolved:
        return "unresolved-move"
    return "local-volume-move"


def print_storage_table_summary(
    title: str,
    planned_tables: list[PlannedTable],
    limit: int = SUMMARY_TABLE_LIMIT,
) -> None:
    print(title)
    for index, planned in enumerate(planned_tables[:limit], start=1):
        table = planned.table
        print(
            f"  {index}. {table.database}.{table.name} rows={table.total_rows} "
            f"local_bytes={table.local_bytes} ({format_bytes(table.local_bytes)}) "
            f"remote_bytes={table.remote_bytes} ({format_bytes(table.remote_bytes)}) "
            f"total_bytes={table.total_bytes} ({format_bytes(table.total_bytes)})"
        )
    if len(planned_tables) > limit:
        print(f"  ... omitted {len(planned_tables) - limit} more tables")
    print()


def print_skipped_table_summary(planned_tables: list[PlannedTable], limit: int = SUMMARY_TABLE_LIMIT) -> None:
    skipped_tables = [planned for planned in planned_tables if planned.reason is not None]
    if not skipped_tables:
        return
    print(f"Top skipped tables by bytes (showing={min(len(skipped_tables), limit)}):")
    for index, planned in enumerate(skipped_tables[:limit], start=1):
        table = planned.table
        print(
            f"  {index}. {table.database}.{table.name} "
            f"rows={table.total_rows} bytes={table.total_bytes} ({format_bytes(table.total_bytes)}) "
            f"reason={planned.reason}"
        )
    if len(skipped_tables) > limit:
        print(f"  ... omitted {len(skipped_tables) - limit} more tables")
    print()


def print_analysis(
    planned_tables: list[PlannedTable],
    skipped_summary_plan: list[PlannedTable] | None = None,
    limit: int = SUMMARY_TABLE_LIMIT,
    topology: StorageTopology | None = None,
) -> None:
    summary = summarize_planned_tables(planned_tables)
    print("Analysis summary:")
    print(
        "  selected: "
        f"tables={summary['selected_tables']} rows={summary['selected_rows']} "
        f"bytes={summary['selected_bytes']} ({format_bytes(summary['selected_bytes'])})"
    )
    print(
        "  eligible: "
        f"tables={summary['eligible_tables']} rows={summary['eligible_rows']} "
        f"bytes={summary['eligible_bytes']} ({format_bytes(summary['eligible_bytes'])})"
    )
    print(
        "  skipped: "
        f"tables={summary['skipped_tables']} rows={summary['skipped_rows']} "
        f"bytes={summary['skipped_bytes']} ({format_bytes(summary['skipped_bytes'])})"
    )
    print()

    topology = topology or StorageTopology(frozenset(), {})
    eligible = [planned for planned in planned_tables if planned.reason is None]
    classified = defaultdict(list)
    for planned in eligible:
        classified[classify_ttl_storage(planned, topology)].append(planned)
    local_only = classified["local-only"]
    local_volume_move = classified["local-volume-move"]
    s3_remote_move = classified["s3-remote-move"]
    unresolved_move = classified["unresolved-move"]
    local_only_local_bytes = sum(planned.table.local_bytes for planned in local_only)
    local_move_local_bytes = sum(planned.table.local_bytes for planned in local_volume_move)
    s3_move_local_bytes = sum(planned.table.local_bytes for planned in s3_remote_move)
    s3_move_remote_bytes = sum(planned.table.remote_bytes for planned in s3_remote_move)
    unresolved_local_bytes = sum(planned.table.local_bytes for planned in unresolved_move)
    print("Local disk impact:")
    print(
        f"  local-only: tables={len(local_only)} "
        f"local_bytes={local_only_local_bytes} ({format_bytes(local_only_local_bytes)})"
    )
    print(
        f"  local-volume-move: tables={len(local_volume_move)} "
        f"local_bytes={local_move_local_bytes} ({format_bytes(local_move_local_bytes)})"
    )
    print(
        f"  S3/remote-move: tables={len(s3_remote_move)} "
        f"local_bytes={s3_move_local_bytes} ({format_bytes(s3_move_local_bytes)}) "
        f"remote_bytes={s3_move_remote_bytes} ({format_bytes(s3_move_remote_bytes)})"
    )
    if unresolved_move:
        print(
            f"  unresolved-move: tables={len(unresolved_move)} "
            f"local_bytes={unresolved_local_bytes} ({format_bytes(unresolved_local_bytes)})"
        )
    print(
        "  total eligible local disk bytes: "
        f"{summary['eligible_local_bytes']} ({format_bytes(summary['eligible_local_bytes'])})"
    )
    print(
        "  exact disk savings: unknown until ZSTD recompression completes; "
        "the value above is the current local data footprint eligible for recompression"
    )
    print()

    reason_counts = Counter(planned.reason for planned in planned_tables if planned.reason is not None)
    if reason_counts:
        print("Skip reasons:")
        for reason, count in reason_counts.most_common():
            reason_bytes = sum(
                planned.table.total_bytes
                for planned in planned_tables
                if planned.reason == reason
            )
            print(f"  {reason}: tables={count} bytes={reason_bytes} ({format_bytes(reason_bytes)})")
        print()

    if local_only:
        print_storage_table_summary(
            f"Top eligible local-only tables by bytes (showing={min(len(local_only), limit)}):",
            local_only,
            limit,
        )
    if local_volume_move:
        print_storage_table_summary(
            f"Top eligible local-volume-move tables by bytes (showing={min(len(local_volume_move), limit)}):",
            local_volume_move,
            limit,
        )
    if s3_remote_move:
        print_storage_table_summary(
            f"Top eligible S3/remote-move tables by bytes (showing={min(len(s3_remote_move), limit)}):",
            s3_remote_move,
            limit,
        )
    if unresolved_move:
        print_storage_table_summary(
            f"Top eligible unresolved-move tables by bytes (showing={min(len(unresolved_move), limit)}):",
            unresolved_move,
            limit,
        )

    print_skipped_table_summary(skipped_summary_plan or planned_tables, limit)


def merge_tables(table_lists: list[list[Table]]) -> list[Table]:
    """Aggregate per-node tables into cluster-level tables by (database, name).

    Row/byte counters are summed across nodes; schema fields (create_query,
    partition_key, storage_policy) are taken from the first node that reports
    the table. Results are sorted by total_bytes descending, matching
    ``fetch_ranked_tables``.
    """
    merged: dict[tuple[str, str], Table] = {}
    for tables in table_lists:
        for table in tables:
            key = (table.database, table.name)
            existing = merged.get(key)
            if existing is None:
                merged[key] = table
                continue
            merged[key] = Table(
                existing.database,
                existing.name,
                existing.create_query,
                existing.partition_key,
                existing.total_rows + table.total_rows,
                existing.total_bytes + table.total_bytes,
                existing.local_bytes + table.local_bytes,
                existing.remote_bytes + table.remote_bytes,
                existing.storage_policy,
            )
    return sorted(merged.values(), key=lambda table: table.total_bytes, reverse=True)


def merge_topologies(topologies: list[StorageTopology]) -> StorageTopology:
    remote_disks: set[str] = set()
    volume_disks: dict[tuple[str, str], tuple[str, ...]] = {}
    for topology in topologies:
        remote_disks |= set(topology.remote_disks)
        volume_disks.update(topology.volume_disks)
    return StorageTopology(frozenset(remote_disks), volume_disks)


def run_cluster_analysis(args: argparse.Namespace, cluster: Cluster) -> int:
    """Fetch tables and storage topology from every node in a cluster and print
    a single cluster-granularity analysis. Node data is summed per table; note
    that replicas holding the same data are double-counted, since node topology
    (shard/replica layout) is not known to this script."""
    fetch_args = argparse.Namespace(**vars(args))
    fetch_args.all = True
    fetch_args.include_system = True

    table_lists: list[list[Table]] = []
    topologies: list[StorageTopology] = []
    reachable = 0
    for index, node in enumerate(cluster.nodes, start=1):
        endpoint = f"{node.host}:{node.port}" if node.port is not None else node.host
        log(f"stage=fetch status=started cluster={cluster.name} node={index}/{len(cluster.nodes)} endpoint={endpoint}")
        try:
            client = create_node_client(args, node)
            table_lists.append(fetch_tables(client, fetch_args))
            topologies.append(fetch_storage_topology(client))
        except Exception as error:
            log(f"stage=fetch status=failed cluster={cluster.name} node={endpoint} error={error}")
            continue
        reachable += 1
        log(f"stage=fetch status=completed cluster={cluster.name} node={endpoint} tables={len(table_lists[-1])}")

    print("=" * 72)
    print(f"Cluster: {cluster.name} (nodes={len(cluster.nodes)} reachable={reachable})")
    print("=" * 72)
    if reachable == 0:
        print("No reachable nodes; skipping analysis.")
        print()
        return 1

    tables = merge_tables(table_lists)
    topology = merge_topologies(topologies)
    planned_tables = plan_tables(tables)
    eligible_tables = [planned.table for planned in planned_tables if planned.reason is None]
    print_table_summary(
        f"Active tables by bytes overall (selected={len(tables)} showing={min(len(tables), SUMMARY_TABLE_LIMIT)}):",
        tables,
    )
    print_table_summary(
        "Active tables by bytes excluding skipped tables "
        f"(selected={len(eligible_tables)} showing={min(len(eligible_tables), SUMMARY_TABLE_LIMIT)}):",
        eligible_tables,
    )
    print_analysis(planned_tables, planned_tables, topology=topology)
    log(f"run status=completed mode=analysis cluster={cluster.name}")
    return 0


def plan_tables(tables: list[Table]) -> list[PlannedTable]:
    return [
        PlannedTable(table, ttl, ttl_base, skip_reason(table, ttl, ttl_base))
        for table in tables
        for ttl in [extract_ttl(table.create_query)]
        for ttl_base in [ttl_base_expression(table.partition_key, extract_column_types(table.create_query))]
    ]


def skipped_table_count(planned_tables: list[PlannedTable]) -> int:
    return sum(1 for planned in planned_tables if planned.reason is not None)


def collect_skipped_summary_plan(client, args: argparse.Namespace, planned_tables: list[PlannedTable]) -> list[PlannedTable]:
    if args.all or skipped_table_count(planned_tables) >= DEFAULT_SKIPPED_SUMMARY_LIMIT:
        return planned_tables

    scan_limit = args.limit
    best_plan = planned_tables
    while skipped_table_count(best_plan) < DEFAULT_SKIPPED_SUMMARY_LIMIT:
        next_limit = min(scan_limit * 2, DEFAULT_SKIPPED_SUMMARY_SCAN_LIMIT)
        if next_limit <= scan_limit:
            break
        summary_args = argparse.Namespace(**vars(args))
        summary_args.limit = next_limit
        log(
            "stage=skipped_summary status=fetching "
            f"limit={next_limit} target_skipped={DEFAULT_SKIPPED_SUMMARY_LIMIT}"
        )
        tables = fetch_tables(client, summary_args)
        best_plan = plan_tables(tables)
        log(
            "stage=skipped_summary status=fetched "
            f"selected={len(best_plan)} skipped={skipped_table_count(best_plan)}"
        )
        scan_limit = next_limit
        if len(best_plan) < scan_limit:
            break
    return best_plan


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


def is_setting_alter(statement: str) -> bool:
    return re.search(r"\bMODIFY\s+SETTING\b", statement, re.IGNORECASE) is not None


def skip_reason(table: Table, ttl: str | None, ttl_base: str | None) -> str | None:
    if table.database in SYSTEM_DATABASES:
        return "system database"
    if not table.partition_key.strip():
        return "empty partition key"
    if ttl and has_recompress(ttl):
        return "already has TTL RECOMPRESS"
    if not ttl or not has_ttl_delete(ttl):
        return "no table TTL DELETE"
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
        setting_statement = next((statement for statement in statements if is_setting_alter(statement)), None)
        if setting_statement:
            print(f"-- planned setting: {setting_statement}")
        else:
            print("-- planned setting: (already satisfied; skipped)")
        print(f"-- planned TTL: {statements[-1]}")
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
    setting_statement = next((statement for statement in statements if is_setting_alter(statement)), None)
    if setting_statement:
        log(f"stage=apply status=setting-started table={index}/{total} name={name}")
        if log_queries:
            log_sql("apply", setting_statement)
        try:
            client.command(setting_statement)
        except Exception as error:
            log(f"stage=apply status=setting-failed table={index}/{total} name={name} error={error}")
            raise
        log(f"stage=apply status=setting-completed table={index}/{total} name={name}")
    else:
        log(f"stage=apply status=setting-skipped table={index}/{total} name={name} reason=already-satisfied")
    wait_for_materialize_ttl_capacity(
        client,
        DEFAULT_MAX_ACTIVE_MATERIALIZE_TTL,
        DEFAULT_MATERIALIZE_TTL_POLL_SECONDS,
    )
    log(f"stage=apply status=ttl-started table={index}/{total} name={name}")
    ttl_statement = statements[-1]
    if log_queries:
        log_sql("apply", ttl_statement)
    try:
        client.command(ttl_statement)
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


def apply_repair_setting_table(
    client,
    index: int,
    total: int,
    table: Table,
    cluster: str | None,
    log_query: bool,
) -> int:
    name = f"{table.database}.{table.name}"
    statement = render_repair_setting_alter(table, cluster)
    log(f"stage=apply_repair status=started table={index}/{total} name={name}")
    if log_query:
        log_sql("apply_repair", statement)
    try:
        client.command(statement)
    except Exception as error:
        log(f"stage=apply_repair status=failed table={index}/{total} name={name} error={error}")
        raise
    log(f"stage=apply_repair status=completed table={index}/{total} name={name}")
    return index


def apply_repair_setting_with_thread_client(
    args: argparse.Namespace,
    index: int,
    total: int,
    table: Table,
    log_query: bool,
) -> int:
    return apply_repair_setting_table(
        get_apply_client(args), index, total, table, args.cluster, log_query
    )


def apply_repair_settings(client, args: argparse.Namespace, tables: list[Table]) -> None:
    total = len(tables)
    log(f"stage=apply_repair status=started tables={total} concurrency={args.apply_concurrency}")
    if args.apply_concurrency == 1:
        for index, table in enumerate(tables, start=1):
            apply_repair_setting_table(
                client, index, total, table, args.cluster, index <= SUMMARY_TABLE_LIMIT
            )
    else:
        with ThreadPoolExecutor(max_workers=args.apply_concurrency) as executor:
            futures = [
                executor.submit(
                    apply_repair_setting_with_thread_client,
                    args,
                    index,
                    total,
                    table,
                    index <= SUMMARY_TABLE_LIMIT,
                )
                for index, table in enumerate(tables, start=1)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise
    log(f"stage=apply_repair status=completed tables={total}")


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
    parser.add_argument(
        "--clusters-dir",
        dest="clusters_dir",
        help=(
            "Path to a pssh-style cluster directory (each *.txt file is a cluster, file "
            "name = cluster name, one node IP per line) or a single such cluster file. "
            "Runs --analysis per cluster, aggregating all nodes into one "
            "cluster-granularity report. Overrides --host."
        ),
    )
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
        "--materialize-ttl-after-modify",
        dest="materialize_ttl_after_modify",
        action="store_true",
        default=False,
        help="Enable automatic historical TTL materialization after MODIFY TTL (by default, materialize_ttl_after_modify = 0 is set)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan",
        action="store_true",
        help="Plan TTL RECOMPRESS changes and output SQL without executing (dry-run)",
    )
    mode.add_argument("--apply", action="store_true", help="Execute the TTL RECOMPRESS plan")
    mode.add_argument(
        "--analysis",
        action="store_true",
        help=(
            "Analyze eligible local disk footprint, separating local-only, local-volume-move, "
            "and S3/remote-move tables (default mode if no action specified)"
        ),
    )
    mode.add_argument(
        "--repair-setting",
        action="store_true",
        help=(
            "Analyze tables with TTL RECOMPRESS that do not explicitly enable "
            "materialize_ttl_recalculate_only, and print the repair SQL"
        ),
    )
    mode.add_argument(
        "--apply-repair",
        action="store_true",
        help=(
            "Run repair-setting analysis, then enable materialize_ttl_recalculate_only "
            "on every table that needs repair"
        ),
    )
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
    if args.clusters_dir:
        try:
            clusters = load_clusters_dir(args.clusters_dir, default_port=args.port)
        except (OSError, ValueError) as error:
            print(f"failed to read clusters dir: {error}", file=sys.stderr)
            return 2
        log(f"stage=clusters status=loaded dir={args.clusters_dir} clusters={len(clusters)}")
        exit_code = 0
        for cluster in clusters:
            if run_cluster_analysis(args, cluster) != 0:
                exit_code = 1
        log(f"run status=completed mode=clusters clusters={len(clusters)}")
        return exit_code
    client = create_client(args)
    if args.repair_setting or args.apply_repair:
        log(
            "stage=fetch_repair_setting status=started "
            f"databases={args.databases or '(all non-system)'} tables={args.tables or '(all)'}"
        )
        try:
            repair_tables = fetch_repair_setting_tables(client, args)
        except Exception as error:
            log(f"stage=fetch_repair_setting status=failed error={error}")
            raise
        repair_plan = plan_repair_settings(repair_tables)
        log(
            "stage=fetch_repair_setting status=completed "
            f"scanned={len(repair_plan.tables)} recompress={len(repair_plan.recompress_tables)} "
            f"repair_needed={len(repair_plan.repair_tables)}"
        )
        print_repair_setting_analysis(repair_plan, args.cluster)
        if args.apply_repair:
            apply_repair_settings(client, args, repair_plan.repair_tables)
        else:
            log("stage=apply_repair status=skipped reason=dry-run; rerun with --apply-repair to execute")
        log(
            f"run status=completed mode={'apply-repair' if args.apply_repair else 'repair-setting'} "
            f"repair_needed={len(repair_plan.repair_tables)}"
        )
        return 0
    # Default to analysis mode if no mode is specified
    if not (args.plan or args.apply or args.analysis):
        args.analysis = True

    fetch_args = argparse.Namespace(**vars(args))
    if args.analysis:
        fetch_args.all = True
        fetch_args.include_system = True
    else:
        fetch_args.include_system = False
    limit_label = "all" if fetch_args.all else str(fetch_args.limit)
    database_label = args.databases or ("(all including system)" if args.analysis else "(all non-system)")
    log(
        "stage=fetch status=started "
        f"limit={limit_label} databases={database_label} "
        f"tables={args.tables or '(all)'}"
    )
    try:
        tables = fetch_tables(client, fetch_args)
    except Exception as error:
        log(f"stage=fetch status=failed error={error}")
        raise
    log(f"stage=fetch status=completed selected={len(tables)}")
    planned_tables = plan_tables(tables)
    skipped_summary_plan = collect_skipped_summary_plan(client, fetch_args, planned_tables)
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
    if args.analysis:
        storage_topology = fetch_storage_topology(client)
        print_analysis(planned_tables, skipped_summary_plan, topology=storage_topology)
        log("run status=completed mode=analysis")
        return 0

    # Only continue with plan/apply if --plan or --apply was specified
    if not (args.plan or args.apply):
        log("run status=completed mode=analysis")
        return 0

    print_skipped_table_summary(skipped_summary_plan)

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
        log("stage=apply status=skipped reason=plan-mode; rerun with --apply to execute")
    log(f"run status=completed mode={'apply' if args.apply else 'plan'} planned={planned} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
