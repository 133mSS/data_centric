import pytest
from uuid import uuid4
import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app.audit import log_decision


class FakeCursor:
    def __init__(self):
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params):
        self.calls.append((sql, params))


class FakeConnection:
    def __init__(self):
        self.fake_cursor = FakeCursor()
    def cursor(self):
        return self.fake_cursor


@pytest.mark.parametrize("decision", ["ALLOW", "DENY", "REDACT", "BLOCK"])
def test_supported_decisions_insert(decision):
    conn = FakeConnection()
    log_decision(
        conn, request_id=uuid4(), user_id=1, stage="retrieval",
        decision=decision, reason="allowed",
    )
    assert len(conn.fake_cursor.calls) == 1
    assert "INSERT INTO audit_log" in conn.fake_cursor.calls[0][0]


def test_unknown_reason_is_not_logged():
    conn = FakeConnection()
    secret = "SECRET_VALUE_123"
    log_decision(
        conn, request_id=uuid4(), user_id=1, stage="output_dlp",
        decision="REDACT", reason=secret,
    )
    params = conn.fake_cursor.calls[0][1]
    assert secret not in params
    assert "unspecified" in params


def test_invalid_stage_rejected_before_db():
    conn = FakeConnection()
    with pytest.raises(ValueError, match="Invalid audit stage"):
        log_decision(
            conn, request_id=uuid4(), user_id=1, stage="bad",
            decision="ALLOW", reason="allowed",
        )
    assert not conn.fake_cursor.calls
