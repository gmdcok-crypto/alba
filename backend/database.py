"""DB 연결 — 로컬 SQLite, Railway/운영은 MySQL (PyMySQL)."""

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

try:
    from pymysql.err import IntegrityError as _MysqlIntegrityError
except ImportError:  # pragma: no cover
    class _MysqlIntegrityError(Exception):
        pass

IntegrityError = (sqlite3.IntegrityError, _MysqlIntegrityError)


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


def on_railway() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_SERVICE_NAME")
        or os.getenv("RAILWAY_PROJECT_ID")
    )


def _env_first(*keys: str) -> str | None:
    for k in keys:
        if k in os.environ:
            return os.environ[k]
    return None


def _db_related_keys_hint() -> str:
    names = sorted(
        k
        for k in os.environ
        if any(x in k.upper() for x in ("MYSQL", "DATABASE", "DB_", "MARIA", "SQL"))
    )
    if not names:
        return "(DB 관련 환경 변수 이름이 하나도 없습니다.)"
    return ", ".join(names[:40]) + ("…" if len(names) > 40 else "")


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


def _is_public_proxy(host: str) -> bool:
    h = host.lower()
    return h.endswith(".proxy.rlwy.net") or h.endswith(".railway.app")


def _find_mysql_url() -> tuple[str, int, str, str, str] | None:
    """사설 URL을 공개 프록시보다 먼저 쓴다."""
    private_keys = (
        "MYSQL_PRIVATE_URL",
        "MYSQL_URL",
        "DATABASE_PRIVATE_URL",
        "DATABASE_URL",
        "MYSQLURL",
    )
    public_keys = ("MYSQL_PUBLIC_URL", "DATABASE_PUBLIC_URL")
    found_public: tuple[str, int, str, str, str] | None = None
    for key in private_keys + public_keys:
        parsed = _parse_mysql_url(os.getenv(key, ""))
        if parsed is None:
            continue
        if _is_public_proxy(parsed[0]) or key in public_keys:
            found_public = found_public or parsed
            continue
        return parsed
    for _k, v in os.environ.items():
        if not v or len(v) < 15:
            continue
        if not v.startswith(("mysql://", "mariadb://", "mysql+", "mariadb+")):
            continue
        parsed = _parse_mysql_url(v)
        if parsed is None:
            continue
        if _is_public_proxy(parsed[0]):
            found_public = found_public or parsed
            continue
        return parsed
    return found_public


def _mysql_params() -> tuple[str, int, str, str, str] | None:
    parsed = _find_mysql_url()

    mysql_host = os.getenv("MYSQLHOST") or os.getenv("MYSQL_HOST")
    mysql_port = os.getenv("MYSQLPORT") or os.getenv("MYSQL_PORT")
    user = (
        os.getenv("DB_USER")
        or os.getenv("MYSQLUSER")
        or os.getenv("MYSQL_USER")
        or os.getenv("MYSQL_USERNAME")
    )
    password = _env_first("DB_PASSWORD", "MYSQLPASSWORD", "MYSQL_PASSWORD")
    database = _env_first("DB_NAME", "MYSQL_DATABASE", "MYSQLDATABASE")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")

    if parsed is not None:
        host, port, url_user, url_password, url_db = parsed
        if mysql_host and _is_public_proxy(host):
            host = mysql_host
            if mysql_port:
                try:
                    port = int(mysql_port)
                except ValueError:
                    pass
        return (
            host,
            port,
            url_user or user or "",
            url_password if url_password is not None else (password or ""),
            url_db or database or "",
        )

    if not user or password is None or not database:
        return None

    host = mysql_host or db_host or "127.0.0.1"
    port_str = mysql_port or db_port or "3306"
    if mysql_host and db_host and _is_public_proxy(db_host):
        host = mysql_host
        if mysql_port:
            port_str = mysql_port
    try:
        port = int(port_str)
    except ValueError:
        port = 3306
    return host, port, user, password, database


def use_mysql() -> bool:
    return _mysql_params() is not None


def get_connection() -> Connection:
    params = _mysql_params()
    if params is None:
        if on_railway():
            raise RuntimeError(
                "Railway에서는 MySQL이 필요합니다. 웹 서비스 Variables에 "
                "MySQL 서비스 변수를 참조로 넣으세요 "
                "(MYSQLHOST, MYSQLPORT, MYSQLUSER, MYSQLPASSWORD, MYSQLDATABASE 또는 MYSQL_URL). "
                f"현재 감지된 관련 키: {_db_related_keys_hint()}"
            )
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
        connect_timeout=8,
        read_timeout=30,
        write_timeout=30,
        init_command="SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci",
    )
    return _MysqlConn(raw)


def get_db() -> Generator[Connection, None, None]:
    conn = get_connection()
    try:
        if conn.kind == "mysql":
            cur = conn.cursor()
            cur.execute("SET time_zone = '+09:00'")
            cur.execute("SET NAMES utf8mb4")
        yield conn
    finally:
        conn.close()
