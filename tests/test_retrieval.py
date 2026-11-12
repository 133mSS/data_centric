import psycopg2
import sys
from pathlib import Path
APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from retrieval import retrieve_chunks
from db_config import get_db_config


def get_user(conn, username):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT username, role, department
            FROM users
            WHERE username = %s
            """,
            (username,)
        )

        row = cur.fetchone()

    if row is None:
        raise ValueError(f"User not found: {username}")

    return {
        "username": row[0],
        "role": row[1],
        "department": row[2],
    }


def run_test(username):
    conn = psycopg2.connect(**get_db_config())

    try:
        user = get_user(conn, username)

        rows = retrieve_chunks(conn, user)

        print(f"\nUser: {username}")
        print(f"Total chunks returned: {len(rows)}")

        for row in rows:
            print(
                f"Chunk #{row[0]} | "
                f"Document #{row[1]} | "
                f"{row[2]} | "
                f"{row[3]} | "
                f"{row[4]}"
            )

    finally:
        conn.close()


if __name__ == "__main__":
    run_test("partner_01")