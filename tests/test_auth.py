"""Unit tests for authentication using deterministic bcrypt/pyotp test doubles."""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

# Test doubles keep these unit tests runnable without external packages installed.
bcrypt = types.ModuleType("bcrypt")
bcrypt.checkpw = lambda plain, hashed: plain == hashed
bcrypt.hashpw = lambda plain, salt: plain
bcrypt.gensalt = lambda: b"test"
sys.modules.setdefault("bcrypt", bcrypt)
pyotp = types.ModuleType("pyotp")
class _TOTP:
    def __init__(self, secret): self.secret = secret
    def verify(self, otp, valid_window=0): return otp == "123456" and valid_window == 1
pyotp.TOTP = _TOTP
sys.modules.setdefault("pyotp", pyotp)

os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"
import auth

class Cursor:
    def __init__(self, row): self.row = row; self.sql = ""
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params): self.sql = sql
    def fetchone(self): return self.row

class Connection:
    def __init__(self, row): self.row = row
    def cursor(self): return Cursor(self.row)

USER_ROW = (7, "hashed-password", "JBSWY3DPEHPK3PXP")
DB_USER_ROW = (7, "nv_dev", "Nhân viên", "Kỹ thuật")

def token_for(payload):
    segment = auth._b64encode(json.dumps(payload, separators=(",", ":")).encode())
    return f"{segment}.{auth._sign(segment)}"

def test_correct_login_returns_token_and_user_is_loaded_from_db():
    token = auth.authenticate(Connection(USER_ROW), "nv_dev", "hashed-password", "123456")
    assert auth.user_from_token(Connection(DB_USER_ROW), token) == {
        "id": 7, "username": "nv_dev", "role": "Nhân viên", "department": "Kỹ thuật"
    }

def test_bad_password_rejected():
    with pytest.raises(auth.AuthenticationError):
        auth.authenticate(Connection(USER_ROW), "nv_dev", "wrong", "123456")

def test_bad_otp_rejected():
    with pytest.raises(auth.AuthenticationError):
        auth.authenticate(Connection(USER_ROW), "nv_dev", "hashed-password", "000000")

def test_expired_token_rejected():
    with pytest.raises(auth.AuthenticationError):
        auth.user_from_token(Connection(DB_USER_ROW), token_for({"uid": 7, "exp": int(time.time()) - 1}))

def test_tampered_token_rejected():
    token = token_for({"uid": 7, "exp": int(time.time()) + 60})
    with pytest.raises(auth.AuthenticationError):
        auth.user_from_token(Connection(DB_USER_ROW), token + "tampered")

def test_missing_user_rejected():
    token = token_for({"uid": 7, "exp": int(time.time()) + 60})
    with pytest.raises(auth.AuthenticationError):
        auth.user_from_token(Connection(None), token)

def test_role_and_department_are_not_taken_from_token():
    token = token_for({"uid": 7, "exp": int(time.time()) + 60, "role": "Ban lãnh đạo", "department": "Toàn công ty"})
    user = auth.user_from_token(Connection(DB_USER_ROW), token)
    assert user["role"] == "Nhân viên"
    assert user["department"] == "Kỹ thuật"
