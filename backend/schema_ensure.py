"""앱 기동 시 테이블 생성."""

from __future__ import annotations

from backend.database import Connection


_SQLITE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      login_id TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stores (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      owner_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      invite_code TEXT NOT NULL UNIQUE,
      lat REAL NULL,
      lng REAL NULL,
      geofence_m INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY (owner_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS store_members (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      store_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      hourly_wage INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL,
      UNIQUE (store_id, user_id),
      FOREIGN KEY (store_id) REFERENCES stores(id),
      FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attendance_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      store_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      event_type TEXT NOT NULL,
      occurred_at TEXT NOT NULL,
      lat REAL NULL,
      lng REAL NULL,
      source TEXT NOT NULL DEFAULT 'MOBILE',
      device_info TEXT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY (store_id) REFERENCES stores(id),
      FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_tokens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      jti TEXT NOT NULL UNIQUE,
      expires_at TEXT NOT NULL,
      revoked INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_user_time ON attendance_events (user_id, store_id, occurred_at)",
    """
    CREATE TABLE IF NOT EXISTS departments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      store_id INTEGER NOT NULL,
      code TEXT NOT NULL,
      name TEXT NOT NULL,
      UNIQUE (store_id, code),
      FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS employees (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      store_id INTEGER NOT NULL,
      employee_no TEXT NOT NULL,
      name TEXT NOT NULL,
      department_id INTEGER NULL,
      hire_date TEXT NULL,
      status TEXT NOT NULL DEFAULT '재직',
      password_hash TEXT NULL,
      auth_status TEXT NOT NULL DEFAULT 'X',
      hourly_wage INTEGER NOT NULL DEFAULT 0,
      UNIQUE (store_id, employee_no),
      FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE,
      FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS employee_refresh_tokens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER NOT NULL,
      jti TEXT NOT NULL UNIQUE,
      expires_at TEXT NOT NULL,
      revoked INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS branch_managers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      store_id INTEGER NOT NULL,
      department_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      UNIQUE (department_id),
      UNIQUE (user_id),
      FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE,
      FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
]

_MYSQL_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      login_id VARCHAR(64) NOT NULL,
      name VARCHAR(64) NOT NULL,
      password_hash VARCHAR(255) NOT NULL,
      role VARCHAR(16) NOT NULL,
      created_at DATETIME(3) NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_users_login (login_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS stores (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      owner_id BIGINT UNSIGNED NOT NULL,
      name VARCHAR(128) NOT NULL,
      invite_code VARCHAR(16) NOT NULL,
      lat DOUBLE NULL,
      lng DOUBLE NULL,
      geofence_m INT NOT NULL DEFAULT 0,
      created_at DATETIME(3) NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_stores_invite (invite_code),
      KEY idx_stores_owner (owner_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS store_members (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      store_id BIGINT UNSIGNED NOT NULL,
      user_id BIGINT UNSIGNED NOT NULL,
      hourly_wage INT NOT NULL DEFAULT 0,
      status VARCHAR(16) NOT NULL DEFAULT 'active',
      created_at DATETIME(3) NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_store_user (store_id, user_id),
      KEY idx_members_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS attendance_events (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      store_id BIGINT UNSIGNED NOT NULL,
      user_id BIGINT UNSIGNED NOT NULL,
      event_type VARCHAR(8) NOT NULL,
      occurred_at DATETIME(3) NOT NULL,
      lat DOUBLE NULL,
      lng DOUBLE NULL,
      source VARCHAR(32) NOT NULL DEFAULT 'MOBILE',
      device_info VARCHAR(255) NULL,
      created_at DATETIME(3) NOT NULL,
      PRIMARY KEY (id),
      KEY idx_events_user_time (user_id, store_id, occurred_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS refresh_tokens (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      user_id BIGINT UNSIGNED NOT NULL,
      jti VARCHAR(64) NOT NULL,
      expires_at DATETIME(3) NOT NULL,
      revoked TINYINT NOT NULL DEFAULT 0,
      created_at DATETIME(3) NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_refresh_jti (jti),
      KEY idx_refresh_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS departments (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      store_id BIGINT UNSIGNED NOT NULL,
      code VARCHAR(32) NOT NULL,
      name VARCHAR(64) NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_dept_store_code (store_id, code),
      KEY idx_dept_store (store_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS employees (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      store_id BIGINT UNSIGNED NOT NULL,
      employee_no VARCHAR(32) NOT NULL,
      name VARCHAR(64) NOT NULL,
      department_id BIGINT UNSIGNED NULL,
      hire_date DATE NULL,
      status VARCHAR(16) NOT NULL DEFAULT '재직',
      password_hash VARCHAR(255) NULL,
      auth_status CHAR(1) NOT NULL DEFAULT 'X',
      hourly_wage INT NOT NULL DEFAULT 0,
      PRIMARY KEY (id),
      UNIQUE KEY uk_emp_store_no (store_id, employee_no),
      KEY idx_emp_store (store_id),
      KEY idx_emp_dept (department_id),
      KEY idx_emp_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS employee_refresh_tokens (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      employee_id BIGINT UNSIGNED NOT NULL,
      jti VARCHAR(64) NOT NULL,
      expires_at DATETIME(3) NOT NULL,
      revoked TINYINT NOT NULL DEFAULT 0,
      created_at DATETIME(3) NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_emp_refresh_jti (jti),
      KEY idx_emp_refresh (employee_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS branch_managers (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      store_id BIGINT UNSIGNED NOT NULL,
      department_id BIGINT UNSIGNED NOT NULL,
      user_id BIGINT UNSIGNED NOT NULL,
      PRIMARY KEY (id),
      UNIQUE KEY uk_bm_dept (department_id),
      UNIQUE KEY uk_bm_user (user_id),
      KEY idx_bm_store (store_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def _column_names(conn: Connection, table: str) -> set[str]:
    cur = conn.cursor()
    if conn.kind == "mysql":
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        rows = cur.fetchall() or []
        return {str(r.get("Field") or r.get("field") or "") for r in rows}
    cur.execute(f"PRAGMA table_info({table})")
    rows = cur.fetchall() or []
    return {str(r.get("name") or "") for r in rows}


def _add_column_if_missing(
    conn: Connection, table: str, column: str, sqlite_sql: str, mysql_sql: str
) -> None:
    if column in _column_names(conn, table):
        return
    cur = conn.cursor()
    col_sql = mysql_sql if conn.kind == "mysql" else sqlite_sql
    table_sql = f"`{table}`" if conn.kind == "mysql" else table
    cur.execute(f"ALTER TABLE {table_sql} ADD COLUMN {col_sql}")


def ensure_schema(conn: Connection) -> None:
    ddl = _MYSQL_DDL if conn.kind == "mysql" else _SQLITE_DDL
    cur = conn.cursor()
    for stmt in ddl:
        cur.execute(stmt)
    _add_column_if_missing(
        conn,
        "attendance_events",
        "employee_id",
        "employee_id INTEGER NULL",
        "employee_id BIGINT UNSIGNED NULL",
    )
    conn.commit()
    cur = conn.cursor()
    try:
        if conn.kind == "mysql":
            cur.execute(
                "CREATE INDEX idx_events_emp_time ON attendance_events (employee_id, store_id, occurred_at)"
            )
        else:
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_emp_time ON attendance_events (employee_id, store_id, occurred_at)"
            )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    conn.commit()
