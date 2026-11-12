"""Provision bcrypt passwords and unique TOTP secrets for app + benchmark users.

Set SEED_DEMO_PASSWORD and database environment variables before running.
Each run rotates demo passwords and MFA secrets; use only for a controlled lab.
"""
import os
import sys
from pathlib import Path

import bcrypt
import psycopg2
import pyotp

# Make `python scripts/seed_users.py` work from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "app"))

from db_config import get_db_config

USERS = [
    ("nv_dev", "Nhân viên", "Kỹ thuật"),
    ("mgr_tech", "Manager", "Kỹ thuật"),
    ("mgr_sales", "Manager", "Kinh doanh"),
    ("ceo_boss", "Ban lãnh đạo", "Toàn công ty"),
    ("partner_01", "Đối tác", None),
    ("bench_employee_01", "Nhân viên", "Kỹ thuật"),
    ("bench_employee_02", "Nhân viên", "Kinh doanh"),
    ("bench_manager_01", "Manager", "Kỹ thuật"),
    ("bench_manager_02", "Manager", "Kinh doanh"),
    ("bench_executive_01", "Ban lãnh đạo", "Toàn công ty"),
    ("bench_partner_01", "Đối tác", None),
]


def main():
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("Set SEED_DEMO_PASSWORD to a value of at least 12 characters.")
    db_config = get_db_config()
    if db_config["dbname"] != "baomatdulieu":
        raise SystemExit(
            "Safety stop: scripts/seed_users.py provisions application fixtures only. "
            "Set POSTGRES_DB=baomatdulieu; benchmark fixtures must use benchmark-specific tooling."
        )
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    conn = psycopg2.connect(**db_config)
    provisions = []
    try:
        with conn:
            with conn.cursor() as cur:
                for username, role, department in USERS:
                    secret = pyotp.random_base32()
                    cur.execute(
                        """INSERT INTO users (username, password_hash, role, department, mfa_secret)
                           VALUES (%s, %s, %s::role_t, %s::dept_t, %s)
                           ON CONFLICT (username) DO UPDATE SET
                             password_hash = EXCLUDED.password_hash,
                             role = EXCLUDED.role,
                             department = EXCLUDED.department,
                             mfa_secret = EXCLUDED.mfa_secret""",
                        (username, password_hash, role, department, secret),
                    )
                    provisions.append((username, secret))
    finally:
        conn.close()
    print("Provisioning URIs (scan with an authenticator app):")
    for username, secret in provisions:
        print(f"{username}: {pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name='BaomatDuLieu RAG')}")
    print("WARNING: running again rotates every demo password and MFA secret.")


if __name__ == "__main__":
    main()
