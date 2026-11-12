"""Password + TOTP authentication and signed access tokens for the RAG app."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

import bcrypt
import pyotp


class AuthenticationError(ValueError):
    """Raised when credentials or an access token are invalid."""


def _secret_key() -> bytes:
    value = os.environ.get("SECRET_KEY", "")
    key = value.encode("utf-8")
    if len(key) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 bytes")
    return key


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload_segment: str) -> str:
    digest = hmac.new(_secret_key(), payload_segment.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def authenticate(conn, username: str, password: str, otp: str) -> str:
    """Validate bcrypt password and TOTP, then return a signed uid/exp token."""
    if not all(isinstance(v, str) and v for v in (username, password, otp)):
        raise AuthenticationError("Invalid credentials")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, password_hash, mfa_secret FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    if row is None:
        raise AuthenticationError("Invalid credentials")
    user_id, password_hash, mfa_secret = row
    try:
        password_ok = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        password_ok = False
    if not password_ok or not mfa_secret:
        raise AuthenticationError("Invalid credentials")
    try:
        otp_ok = pyotp.TOTP(mfa_secret).verify(otp, valid_window=1)
    except (TypeError, ValueError):
        otp_ok = False
    if not otp_ok:
        raise AuthenticationError("Invalid credentials")

    payload = {"uid": int(user_id), "exp": int(time.time()) + 3600}
    payload_segment = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_segment}.{_sign(payload_segment)}"


def user_from_token(conn, token: str) -> dict:
    """Verify token and load authorization attributes from the database."""
    if not isinstance(token, str) or token.count(".") != 1:
        raise AuthenticationError("Invalid token")
    payload_segment, signature = token.split(".", 1)
    try:
        expected = _sign(payload_segment)
        if not hmac.compare_digest(signature, expected):
            raise AuthenticationError("Invalid token")
        payload = json.loads(_b64decode(payload_segment).decode("utf-8"))
        uid, exp = payload["uid"], payload["exp"]
        if not isinstance(uid, int) or not isinstance(exp, int) or exp <= int(time.time()):
            raise AuthenticationError("Invalid or expired token")
    except AuthenticationError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Invalid token") from exc

    with conn.cursor() as cur:
        cur.execute("SELECT id, username, role, department FROM users WHERE id = %s", (uid,))
        row = cur.fetchone()
    if row is None:
        raise AuthenticationError("Invalid token subject")
    return {"id": row[0], "username": row[1], "role": row[2], "department": row[3]}
