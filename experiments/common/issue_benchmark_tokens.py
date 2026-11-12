"""Issue benchmark tokens for all fixture users through the real auth flow.

Run from the project root in PowerShell. This is for synthetic local lab users only.
The demo password is read from SEED_DEMO_PASSWORD (loaded by load_lab_env.ps1),
with a hidden prompt as a fallback. Each user's current TOTP is generated from
that fixture account's mfa_secret, then app.auth.authenticate() validates both.
No token assignments are printed unless every configured user authenticates.
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import psycopg2
import pyotp
from auth import AuthenticationError, authenticate
from controlled_rag import get_db_config

USERS = ("nv_dev", "mgr_tech", "mgr_sales", "partner_01", "ceo_boss")


def ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> int:
    password = __import__("os").environ.get("SEED_DEMO_PASSWORD") or getpass.getpass(
        "Shared demo password (hidden): "
    )
    if not password:
        print("Token issuance failed: demo password is empty.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(**get_db_config())
    assignments: list[str] = []
    try:
        for username in USERS:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT mfa_secret FROM users WHERE username = %s",
                    (username,),
                )
                row = cur.fetchone()
            if not row or not row[0]:
                print(
                    f"Token issuance failed: fixture user or MFA secret missing for {username}.",
                    file=sys.stderr,
                )
                return 1

            # Generate a fresh OTP from this synthetic fixture user's own secret.
            otp = pyotp.TOTP(row[0]).now()
            try:
                token = authenticate(conn, username, password, otp)
            except AuthenticationError:
                print(
                    f"Token issuance failed: authentication rejected for {username}. "
                    "Check that SEED_DEMO_PASSWORD matches the current seeded accounts.",
                    file=sys.stderr,
                )
                return 1

            env_name = "RAG_BENCH_TOKEN_" + "".join(
                ch if ch.isalnum() else "_" for ch in username.upper()
            )
            assignments.append(f"$env:{env_name} = {ps_single_quote(token)}")
            print(f"Authenticated benchmark user: {username}", file=sys.stderr)
    finally:
        conn.close()

    # Emit assignments only after all users succeed, preventing partial setup.
    print("\n".join(assignments))
    print(f"Issued tokens for all {len(USERS)} benchmark users.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Do not print connection strings or secret values.
        print(f"Token issuance failed ({type(exc).__name__}). Check database/configuration.", file=sys.stderr)
        raise SystemExit(1)
