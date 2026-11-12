"""Issue lab-only auth tokens, then run the WP7 prompt-injection experiment."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
EXPERIMENT = ROOT / "experiments" / "prompt_injection" / "prompt_injection_test.py"
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
        raise SystemExit("SEED_DEMO_PASSWORD missing/too short; set the lab demo password used by seed_users.py.")
    if len(os.environ.get("SECRET_KEY", "").encode("utf-8")) < 32:
        raise SystemExit("SECRET_KEY missing or shorter than 32 bytes; check .env.")

    import psycopg2
    import pyotp
    from auth import authenticate
    from db_config import get_db_config

    users = sorted({case["user"] for case in runpy.run_path(str(EXPERIMENT))["CASES"]})
    tokens = {}
    with psycopg2.connect(**get_db_config()) as conn:
        with conn.cursor() as cur:
            for username in users:
                cur.execute("SELECT mfa_secret FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                if not row or not row[0]:
                    raise SystemExit(f"MFA not provisioned for WP7 fixture user: {username}")
                tokens[username] = authenticate(conn, username, password, pyotp.TOTP(row[0]).now())

    for username, token in tokens.items():
        env_name = "RAG_BENCH_TOKEN_" + "".join(ch if ch.isalnum() else "_" for ch in username.upper())
        os.environ[env_name] = token

    print(f"Issued signed lab tokens for {len(tokens)} WP7 users through app.auth.authenticate().")
    print("Starting WP7; tokens, OTPs, passwords, raw answers, and sensitive values are not printed.")
    runpy.run_path(str(EXPERIMENT), run_name="__main__")


if __name__ == "__main__":
    main()
