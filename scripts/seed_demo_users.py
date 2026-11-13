"""Provision isolated Demo users and fresh TOTP secrets in baomatdulieu_demo.

The password is entered once for this five-user classroom fixture set. Existing
users are never rotated unless --rotate is explicitly supplied.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

import bcrypt
import psycopg2
import pyotp

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from db_config import DEMO_DATABASE_NAME, get_demo_db_config  # noqa: E402

USERS = (
    ("nv_dev", "Nhân viên", "Kỹ thuật"),
    ("mgr_tech", "Manager", "Kỹ thuật"),
    ("mgr_sales", "Manager", "Kinh doanh"),
    ("ceo_boss", "Ban lãnh đạo", "Toàn công ty"),
    ("partner_01", "Đối tác", None),
)


def read_password():
    password = getpass.getpass("Mat khau demo (toi thieu 12 ky tu): ")
    confirmation = getpass.getpass("Nhap lai mat khau demo: ")
    if password != confirmation:
        raise SystemExit("Hai lan nhap mat khau khong khop.")
    if len(password) < 12:
        raise SystemExit("Mat khau demo phai co it nhat 12 ky tu.")
    return password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Explicitly replace passwords and MFA secrets for the five Demo accounts.",
    )
    args = parser.parse_args()

    config = get_demo_db_config()
    if config["dbname"] != DEMO_DATABASE_NAME:
        raise SystemExit("Safety stop: wrong Demo database.")
    password = read_password()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    provisions = []
    with psycopg2.connect(connect_timeout=10, **config) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            if cur.fetchone()[0] != DEMO_DATABASE_NAME:
                raise SystemExit("Safety stop: connected to an unexpected database.")
            cur.execute(
                "SELECT username FROM users WHERE username = ANY(%s)",
                ([item[0] for item in USERS],),
            )
            existing = {row[0] for row in cur.fetchall()}
            if existing and not args.rotate:
                raise SystemExit(
                    "Demo fixture accounts already exist. No change was made. "
                    "Use --rotate only when you intend to replace their passwords and MFA."
                )
            if existing and existing != {item[0] for item in USERS}:
                raise SystemExit(
                    "Only some fixture accounts exist. Inspect the Demo users table before rotating."
                )

            for username, role, department in USERS:
                secret = pyotp.random_base32()
                cur.execute(
                    """
                    INSERT INTO users
                        (username, password_hash, role, department, mfa_secret)
                    VALUES (%s, %s, %s::role_t, %s::dept_t, %s)
                    ON CONFLICT (username) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role,
                        department = EXCLUDED.department,
                        mfa_secret = EXCLUDED.mfa_secret
                    """,
                    (username, password_hash, role, department, secret),
                )
                uri = pyotp.TOTP(secret).provisioning_uri(
                    name=username,
                    issuer_name="BaomatDuLieu RAG Demo",
                )
                provisions.append((username, secret, uri))

    print(f"Provisioned {len(provisions)} accounts in {DEMO_DATABASE_NAME}.")
    print("All five accounts use the password entered above.")
    print("Add each TOTP secret to an Authenticator app now; these values are shown only once.")
    for username, secret, uri in provisions:
        print(f"\n[{username}]")
        print(f"TOTP secret: {secret}")
        print(f"Provisioning URI: {uri}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
