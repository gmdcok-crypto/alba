"""
MySQL/SQLite 에 알바근태 테이블을 생성합니다. (CREATE TABLE IF NOT EXISTS)

사용 (프로젝트 루트):
  python scripts/apply_schema.py

연결:
  Railway 웹 서비스와 같이 MYSQL_URL / MYSQLHOST 등
  또는 로컬 SQLite (data/alba.db)

mysql.railway.internal 은 Railway 사설망 전용입니다. PC에서는 접속되지 않습니다.
로컬에서 Railway DB를 직접 만지려면 MYSQL_PUBLIC_URL 을 쓰세요.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import get_connection, use_mysql  # noqa: E402
from backend.schema_ensure import ensure_schema  # noqa: E402


def main() -> None:
    conn = get_connection()
    try:
        ensure_schema(conn)
        cur = conn.cursor()
        if conn.kind == "mysql":
            cur.execute("SHOW TABLES")
            rows = cur.fetchall() or []
            names = []
            for row in rows:
                names.append(str(next(iter(row.values()))))
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            names = [str(r["name"]) for r in (cur.fetchall() or [])]
        print(f"ok db={'mysql' if use_mysql() else 'sqlite'}")
        for n in names:
            print(f"  - {n}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
