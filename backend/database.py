"""DB 연결 — 로컬 SQLite, 운영 MariaDB/MySQL (PyMySQL)."""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any, Union
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

DictCursor = "dict"


class _SqliteCursor:
    def __init__(self, raw: sqlite3.Cursor) -> None:
        self._raw = raw
        self.lastrowid = 0
        self.description = None

    def execute(self, sql: str, params: tuple | list | None = None) -> "_SqliteCursor":
        converted = sql.replace("%s", "?")
        self._raw.execute(converted, params or ())
        self.lastrowid = self._raw.lastrowid or 0
        self.description = self._raw.description
        return self

    def fetchone(self) -> dict[str, Any] | None:
        row = self._raw.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._raw.fetchall()]


class _SqliteConn:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self.kind = "sqlite"

    def cursor(self, _factory: object = None) -> _SqliteCursor:
        return _SqliteCursor(self._conn.cursor())

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class _MysqlConn:
    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self.kind = "mysql"

    def cursor(self, _factory: object = None) -> Any:
        from pymysql.cursors import DictCursor as PyDictCursor

        return self._raw.cursor(PyDictCursor)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


Connection = Union[_SqliteConn, _MysqlConn]


def _parse_mysql_url(url: str) -> tuple[str, int, str, str, str] | None:
    if not url or not re.match(r"^(mysql|mariadb)(\+[^:]+)?://", url, re.I):
        return None
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    db = (parsed.path or "").lstrip("/").split("/")[0]
    port = parsed.port or 3306
    if not user or not db:
        return None
    return parsed.hostname, port, user, password, db


def _find_mysql_url() -> tuple[str, int, str, str, str] | None:
    for key in (
        "DATABASE_URL",
        "MYSQL_URL",
        "MYSQL_PRIVATE_URL",
        "MYSQL_PUBLIC_URL",
    ):
        parsed = _parse_mysql_url(os.getenv(key, ""))
        if parsed is not None:
            return parsed
    return None


def _mysql_params() -> tuple[str, int, str, str, str] | None:
    parsed = _find_mysql_url()
    if parsed is not None:
        return parsed

    user = os.getenv("DB_USER") or os.getenv("MYSQLUSER") or os.getenv("MYSQL_USER")
    database = os.getenv("DB_NAME") or os.getenv("MYSQL_DATABASE") or os.getenv("MYSQLDATABASE")
    password = os.getenv("DB_PASSWORD")
    if password is None:
        password = os.getenv("MYSQLPASSWORD") or os.getenv("MYSQL_PASSWORD")
    host = os.getenv("DB_HOST") or os.getenv("MYSQLHOST") or os.getenv("MYSQL_HOST")
    if not user or not database or password is None:
        return None
    port_str = os.getenv("DB_PORT") or os.getenv("MYSQLPORT") or os.getenv("MYSQL_PORT") or "3306"
    try:
        port = int(port_str)
    except ValueError:
        port = 3306
    return host or "127.0.0.1", port, user, password, database


def use_mysql() -> bool:
    return _mysql_params() is not None


def get_connection() -> Connection:
    params = _mysql_params()
    if params is None:
        return _SqliteConn(_ROOT / "data" / "alba.db")

    import pymysql

    host, port, user, password, database = params
    raw = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=30,
        write_timeout=30,
    )
    return _MysqlConn(raw)


def get_db() -> Generator[Connection, None, None]:
    conn = get_connection()
    try:
        if conn.kind == "mysql":
            cur = conn.cursor()
            cur.execute("SET time_zone = '+09:00'")
        yield conn
    finally:
        conn.close()
