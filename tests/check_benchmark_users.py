"""Print benchmark fixtures from the isolated benchmark database.

Run from the project root after loading the local .env:
    python .\\tests\\check_benchmark_users.py
"""
from pathlib import Path
import sys

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from db_config import get_benchmark_db_config  # noqa: E402


def main():
    with psycopg2.connect(**get_benchmark_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT username, role::text, department::text
                FROM users
                WHERE username LIKE 'bench_%'
                ORDER BY username;
            """)
            rows = cur.fetchall()
            for row in rows:
                print(row)
            print(f"\nTotal benchmark users: {len(rows)}")


if __name__ == "__main__":
    main()
