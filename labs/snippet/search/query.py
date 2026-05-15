import os
import logging
import mysql.connector

logger = logging.getLogger(__name__)


def _get_env(name: str, default: str) -> str:
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def get_conn():
    """
    Create and return a MySQL-compatible connection to Doris.

    Env overrides (optional):
      DORIS_HOST, DORIS_PORT, DORIS_USER, DORIS_PASSWORD
    Defaults match the other scripts in this repo.
    """
    host = _get_env("DORIS_HOST", "127.0.0.1")
    port_str = _get_env("DORIS_PORT", "6937")  # MySQL protocol port
    user = _get_env("DORIS_USER", "root")
    password = _get_env("DORIS_PASSWORD", "")

    try:
        port = int(port_str)
    except ValueError:
        logger.warning(f"Invalid DORIS_PORT '{port_str}', falling back to 6937")
        port = 6937

    logger.info(f"Connecting to Doris at {host}:{port} as '{user}'")
    try:
        conn = mysql.connector.connect(
            user=user,
            password=password,
            host=host,
            port=port,
        )
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Failed to connect to Doris/MySQL: {err}")
        raise
