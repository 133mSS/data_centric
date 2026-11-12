"""Run the public-entrypoint leakage benchmark using real auth-issued fixture tokens.

Test-only helper: it uses the seeded demo password and stored TOTP seeds to
produce a current OTP, calls app.auth.authenticate(), and runs the benchmark
in-process. It never prints or persists passwords, OTPs, TOTP seeds, or tokens.
Use only against the controlled lab database.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
BENCHMARK = ROOT / "experiments" / "answer_leakage" / "answer_leakage_test_public_entrypoints.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def load_dotenv_without_overrides(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def main() -> None:
    load_dotenv_without_overrides(ROOT / ".env")
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("SEED_DEMO_PASSWORD missing/too short; set it to the demo password used by seed_users.py.")
    if len(os.environ.get("SECRET_KEY", "").encode("utf-8")) < 32:
        raise SystemExit("SECRET_KEY missing or shorter than 32 bytes; check .env.")

    import psycopg2
    import pyotp
    from auth import authenticate
    from db_config import get_db_config

    fixture_users = ("nv_dev", "mgr_tech", "mgr_sales", "ceo_boss", "partner_01")
    tokens = {}
    with psycopg2.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            for username in fixture_users:
                cur.execute("SELECT mfa_secret FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                if not row or not row[0]:
                    raise SystemExit(f"MFA not provisioned for fixture user: {username}")
                otp = pyotp.TOTP(row[0]).now()
                tokens[username] = authenticate(conn, username, password, otp)

    for username, token in tokens.items():
        env_name = "RAG_BENCH_TOKEN_" + "".join(ch if ch.isalnum() else "_" for ch in username.upper())
        os.environ[env_name] = token

    if not BENCHMARK.exists():
        raise SystemExit(f"Benchmark script not found: {BENCHMARK}")
    print("Issued signed tokens through app.auth.authenticate() for 5 fixture users.")
    print("Starting public-entrypoint benchmark; credentials and tokens will not be printed.")
    runpy.run_path(str(BENCHMARK), run_name="__main__")


if __name__ == "__main__":
    main()
