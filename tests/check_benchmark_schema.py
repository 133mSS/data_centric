"""Print the key benchmark schema using the isolated benchmark DB config.

Run from the project root after loading the local .env:
    python .\\tests\\check_benchmark_schema.py
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
    config = get_benchmark_db_config()
    with psycopg2.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'users', 'documents', 'chunks', 'benchmark_query_cases',
                      'benchmark_runs', 'benchmark_performance_results',
                      'benchmark_case_results'
                  )
                ORDER BY table_name, ordinal_position;
            """)
            for row in cur.fetchall():
                print(row)


if __name__ == "__main__":
    main()
