#!/usr/bin/env python3
"""
Run a Doris vector TOP-K query. Prefer server-side prepared statements when
possible (MySQL binary protocol), and gracefully fall back to text mode.

SQL shape:

	SELECT id,
		   l2_distance_approximate(embedding, [..query_vector..]) AS distance,
		   category
	FROM <table>
	ORDER BY l2_distance_approximate(embedding, [..query_vector..])
	LIMIT ?;

Notes:
- Doris does not support the SQL keywords PREPARE/EXECUTE, but may speak the
  MySQL prepared-statement protocol. We attempt cursor(prepared=True) first.
- Identifiers (table) and complex literals (the vector) cannot be parameter
  markers. We therefore inline those after validation and only bind LIMIT.
"""
from __future__ import annotations

import argparse
import logging
import time
import sys
import re
from typing import List, Optional, Tuple

import mysql.connector

# Module logger
logger = logging.getLogger(__name__)


def parse_vector(vec_arg: str) -> str:
	"""Return a Doris-compatible array literal string from input.

	Accepts either:
	  - "[0.1, 0.2, 0.3]" (passed through), or
	  - "0.1,0.2,0.3" (CSV -> "[0.1, 0.2, 0.3]")
	"""
	s = vec_arg.strip()
	if s.startswith("[") and s.endswith("]"):
		return s
	# CSV -> list of floats
	parts = [p.strip() for p in s.split(",") if p.strip()]
	if not parts:
		raise ValueError("vector is empty")
	floats: List[float] = []
	for p in parts:
		try:
			floats.append(float(p))
		except Exception as e:
			raise ValueError(f"invalid float in vector: {p}") from e
	return "[" + ", ".join(str(x) for x in floats) + "]"


_FLOAT_RE = re.compile(r"[-+]?((?:\d*\.\d+)|(?:\d+))(?:[eE][-+]?\d+)?")


def estimate_vector_dim(vector_literal: str) -> int:
	"""Best-effort dimension estimate from the vector literal string."""
	return len(_FLOAT_RE.findall(vector_literal))


ALLOWED_TABLE_RE = re.compile(r"^[A-Za-z0-9_.$]+(\.[A-Za-z0-9_.$]+)?$")
ALLOWED_IDENT_RE = re.compile(r"^[A-Za-z0-9_.$]+$")


def validate_table_name(name: str) -> None:
	"""Basic allowlist validation for db.table or table.

	Prevents injection when concatenating into the prepared SQL text.
	"""
	if not ALLOWED_TABLE_RE.match(name):
		raise ValueError(
			"invalid table name; only letters, digits, _, $, . allowed, optionally db.table"
		)


def parse_extra_columns(extra: str) -> List[str]:
	"""Parse and validate a comma-separated list of extra columns.

	Returns a list like ["category", "title"] or empty list when none.
	"""
	extra = (extra or "").strip()
	if not extra:
		return []
	cols = []
	for raw in extra.split(","):
		col = raw.strip()
		if not col:
			continue
		if not ALLOWED_IDENT_RE.match(col):
			raise ValueError(f"invalid column identifier: {col}")
		cols.append(col)
	return cols


def abbrev(text: str, max_len: int = 300) -> str:
	"""Abbreviate long text for logging."""
	if len(text) <= max_len:
		return text
	return text[: max_len - 20] + " ... [truncated] ..."



def run_query(host: str, port: int, user: str, password: str, database: Optional[str],
			  table: str, vector_literal: str, topk: int, extra_cols: Optional[List[str]] = None,
			  force_prepared: bool = True, verbose_sql: bool = False) -> List[tuple]:
	conn = None
	cursor = None
	mode_used = ""
	try:
		logger.debug("Connecting to Doris/MySQL host=%s port=%s user=%s database=%s",
					 host, port, user, database)
		t0 = time.monotonic()
		conn = mysql.connector.connect(
			user=user,
			password=password,
			host=host,
			port=port,
		)
		logger.debug("Connection established in %.3fs", time.monotonic() - t0)

		# Issue USE <database> with a plain text cursor first; Doris rejects preparing USE.
		if database:
			try:
				_text_cur = conn.cursor()
				_text_cur.execute(f"USE `{database}`")
				_text_cur.close()
				logger.debug("Using database `%s` (via text cursor)", database)
			except Exception:
				logger.exception("Failed to USE database %s", database)
				raise

		# Now choose the main cursor for the actual query.
		if force_prepared:
			try:
				cursor = conn.cursor(prepared=True)
				mode_used = "prepared"
				logger.debug("Using server-side prepared cursor")
			except Exception:
				cursor = conn.cursor()
				mode_used = "text"
				logger.debug("Prepared cursor unavailable; falling back to text mode")
		else:
			cursor = conn.cursor()
			mode_used = "text"
			logger.debug("Using text mode cursor (no-prepared)")

		# Build SQL with validated table and vector literal; attempt to bind LIMIT as parameter.
		select_extra = ""
		if extra_cols:
			select_extra = ", " + ", ".join(extra_cols)
		sql = (
			f"SELECT id, l2_distance_approximate(embedding, {vector_literal}) AS distance{select_extra} "
			f"FROM {table} "
			f"ORDER BY l2_distance_approximate(embedding, {vector_literal}) LIMIT %s"
		)
		dim = estimate_vector_dim(vector_literal)
		logger.debug("Query dim=%s table=%s topk=%s extra_cols=%s", dim, table, topk, extra_cols or [])
		if verbose_sql:
			logger.debug("SQL: %s", abbrev(sql))
		else:
			logger.debug("SQL length=%d chars (enable --verbose-sql to print SQL)", len(sql))

		try:
			t1 = time.monotonic()
			cursor.execute(sql, (int(topk),))
			exec_dur = time.monotonic() - t1
			rows = cursor.fetchall()
			logger.info("Executed via %s; fetch %d rows in %.3fs", mode_used, len(rows), exec_dur)
		except Exception as prepared_err:
			# Fallback: some servers disallow parameter markers in LIMIT with server-side prep.
			# Re-execute in text mode with the LIMIT rendered inline if prepared failed.
			if mode_used == "prepared":
				try:
					cursor.close()
					cursor = conn.cursor()  # text mode
					sql_text = sql.replace("LIMIT %s", f"LIMIT {int(topk)}")
					if verbose_sql:
						logger.debug("Fallback SQL: %s", abbrev(sql_text))
					else:
						logger.debug("Fallback SQL length=%d chars", len(sql_text))
					t2 = time.monotonic()
					cursor.execute(sql_text)
					exec_dur = time.monotonic() - t2
					rows = cursor.fetchall()
					logger.info("Executed via text fallback; fetch %d rows in %.3fs", len(rows), exec_dur)
				except Exception:
					logger.exception("Prepared mode failed and text fallback also failed")
					raise prepared_err
			else:
				logger.exception("Execution failed in text mode")
				raise
		return rows
	finally:
		try:
			if cursor is not None:
				cursor.close()
		finally:
			if conn is not None and conn.is_connected():
				conn.close()


def main(argv: List[str]) -> int:
	parser = argparse.ArgumentParser(description="Run Doris vector TOP-K (prefers server-side prepared statements)")
	parser.add_argument("--host", default="127.0.0.1", help="Doris/MySQL host")
	parser.add_argument("--port", type=int, default=6937, help="Doris/MySQL port")
	parser.add_argument("--user", default="root", help="User")
	parser.add_argument("--password", default="", help="Password")
	parser.add_argument("--database", default="vector_test", help="Database to USE")
	parser.add_argument("--table", required=True, help="Table name (optionally db.table)")
	parser.add_argument(
		"--vector",
		required=True,
		help="Vector: either '[v1, v2, ...]' or 'v1,v2,...'",
	)
	parser.add_argument("--topk", type=int, default=5, help="Top-K limit")
	parser.add_argument(
		"--extra-cols",
		default="",
		help="Comma-separated extra columns to include (e.g. 'category,title'). Default none.",
	)
	parser.add_argument(
		"--no-prepared",
		action="store_true",
		help="Force text mode (do not use server prepared statements)",
	)
	parser.add_argument(
		"--debug",
		action="store_true",
		help="Enable debug logging (overrides --log-level)",
	)
	parser.add_argument(
		"--log-level",
		default="INFO",
		choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
		help="Logging level (default INFO)",
	)
	parser.add_argument(
		"--verbose-sql",
		action="store_true",
		help="Log full SQL text (may be long)",
	)

	args = parser.parse_args(argv)

	# Configure logging
	level = logging.DEBUG if args.debug else getattr(logging, str(args.log_level).upper(), logging.INFO)
	logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

	# Validate/prepare inputs
	validate_table_name(args.table)
	vector_literal = parse_vector(args.vector)
	extra_cols = parse_extra_columns(args.extra_cols)

	safe_args = {
		"host": args.host,
		"port": args.port,
		"user": args.user,
		"database": args.database,
		"table": args.table,
		"topk": args.topk,
		"extra_cols": extra_cols,
		"prepared": not args.no_prepared,
		"verbose_sql": args.verbose_sql,
	}
	logger.debug("Args: %s", safe_args)

	rows = run_query(
		host=args.host,
		port=args.port,
		user=args.user,
		password=args.password,
		database=args.database,
		table=args.table,
		vector_literal=vector_literal,
		topk=args.topk,
		extra_cols=extra_cols,
		force_prepared=(not args.no_prepared),
		verbose_sql=args.verbose_sql,
	)

	# Print results
	# Print header + rows dynamically
	# cursor.description is not available here anymore; reformat based on known columns
	headers = ["id", "distance"] + extra_cols
	print("\t".join(headers))
	for r in rows:
		fields = [str(v) for v in r]
		print("\t".join(fields))

	return 0


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))

