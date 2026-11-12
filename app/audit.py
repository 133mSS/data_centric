"""Minimal safe audit logging for WP2."""
from uuid import UUID

VALID_DECISIONS = {"ALLOW", "DENY", "REDACT", "BLOCK"}
VALID_STAGES = {"retrieval", "output_dlp"}
SAFE_REASONS = {
    "allowed", "denied", "no-read-up", "department mismatch",
    "clearance+department ok", "sensitive_match", "policy_violation",
    "processing_error", "unspecified",
}


def log_decision(
    conn, *, request_id, user_id, stage, decision, reason,
    document_id=None, chunk_id=None, rule_id=None, query_text=None,
    release_context=None, policy_version="v1",
):
    if stage not in VALID_STAGES:
        raise ValueError("Invalid audit stage")
    if decision not in VALID_DECISIONS:
        raise ValueError("Invalid audit decision")
    try:
        request_id = str(UUID(str(request_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid request_id") from exc

    # Do not allow arbitrary policy/error strings into reason.
    safe_reason = reason if isinstance(reason, str) and reason in SAFE_REASONS else "unspecified"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (
                request_id, user_id, stage, decision, reason, rule_id,
                document_id, chunk_id, query_text, release_context,
                policy_version
            )
            VALUES (
                %s, %s, %s, %s::decision_t, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                request_id, user_id, stage, decision, safe_reason, rule_id,
                document_id, chunk_id, query_text, release_context, policy_version,
            ),
        )
