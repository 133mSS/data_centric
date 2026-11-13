"""Local-only demo web server for the Data-Centric RAG lab project.

The UI calls the existing authentication and controlled-RAG application modules.
This server is intended for a local classroom demonstration, not production use.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "demo_web"
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

HOST = "127.0.0.1"  # Intentionally local-only; do not expose the demo server to the network.
PORT = int(os.environ.get("DEMO_PORT", "8765"))
MAX_BODY = 32 * 1024
LOGIN_WINDOW_SECONDS = 600
LOGIN_MAX_FAILURES = 6
_LOGIN_FAILURES: dict[str, deque[float]] = defaultdict(deque)

ROLE_CLEARANCE = {"Đối tác": 0, "Nhân viên": 1, "Manager": 2, "Ban lãnh đạo": 3}
CLASSIFICATION_LEVEL = {"Công khai": 0, "Nội bộ": 1, "Mật": 2, "Tối mật": 3}
FIXTURE_USERS = ("nv_dev", "mgr_tech", "mgr_sales", "partner_01", "ceo_boss")
DEFAULT_RELEASE_CONTEXT = "SHARE_SUMMARY"  # Unknown-role fallback; resolved release context comes from Controlled RAG.


def _db_config():
    from db_config import get_db_config
    config = get_db_config()
    if config.get("dbname") != "baomatdulieu":
        raise RuntimeError("Demo server must connect to application database 'baomatdulieu'.")
    return config


def _connect():
    import psycopg2
    config = _db_config()
    return psycopg2.connect(connect_timeout=5, **config)


@contextmanager
def _db_session():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def _user_payload(user: dict) -> dict:
    return {
        "id": int(user["id"]),
        "username": str(user["username"]),
        "role": str(user["role"]),
        "department": user["department"],
        "clearance": ROLE_CLEARANCE.get(str(user["role"]), 0),
        "clearance_label": ["Public", "Internal", "Secret", "Top Secret"][ROLE_CLEARANCE.get(str(user["role"]), 0)],
    }


def _verify_user(token: str) -> dict:
    if not token:
        raise PermissionError("Phiên đăng nhập không tồn tại hoặc đã hết hạn.")
    from auth import user_from_token
    with _db_session() as conn:
        user = user_from_token(conn, token)
    return user


def _json_file(path: Path):
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _latest_file(folder: Path, pattern: str, exclude=()):
    candidates = [p for p in folder.glob(pattern) if not any(x in p.name for x in exclude)]
    return max(candidates, key=lambda p: p.name) if candidates else None


def _read_csv(path: Path):
    if not path or not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "t"}


def _experiment_summary() -> dict:
    results = ROOT / "results"
    answer_path = _latest_file(results, "answer_leakage_summary_*.json")
    injection_path = _latest_file(results, "prompt_injection_summary_*.json")
    ablation_path = _latest_file(results, "wp8_ablation_summary_*.json", exclude=("with_ci",))

    answer = _json_file(answer_path) if answer_path else None
    injection = _json_file(injection_path) if injection_path else None
    ablation = _json_file(ablation_path) if ablation_path else None

    wp6_rows = _read_csv(results / "wp6_retrieval_matrix_seed4206.csv")
    wp6 = None
    if wp6_rows:
        passed = sum(1 for row in wp6_rows if _truthy(row.get("pass", "")))
        allowed = sum(1 for row in wp6_rows if row.get("actual") == "ALLOW")
        denied = sum(1 for row in wp6_rows if row.get("actual") == "DENY")
        wp6 = {"checks": len(wp6_rows), "passed": passed, "failed": len(wp6_rows) - passed,
               "pass_rate": round(passed / len(wp6_rows) * 100, 1) if wp6_rows else 0,
               "allow": allowed, "deny": denied}

    benchmark_dir = results / "benchmark_v1"
    dataset_rows = _read_csv(benchmark_dir / "benchmark_dataset_counts.csv")
    datasets = [{
        "scale": int(r.get("dataset_scale", 0)),
        "documents": int(r.get("document_count", 0)),
        "chunks": int(r.get("chunk_count", 0)),
        "embedded_chunks": int(r.get("chunks_with_embedding", 0)),
    } for r in dataset_rows]

    perf_rows = _read_csv(benchmark_dir / "benchmark_performance_results.csv")
    latency = {}
    latency_n = defaultdict(int)
    for row in perf_rows:
        if _truthy(row.get("warmup", "false")):
            continue
        variant = row.get("system_variant", "unknown")
        try:
            latency[variant] = latency.get(variant, 0.0) + float(row.get("total_retrieval_ms") or 0)
            latency_n[variant] += 1
        except (TypeError, ValueError):
            continue
    latency = {k: round(v / latency_n[k], 2) for k, v in latency.items() if latency_n[k]}

    benchmark_cases = _read_csv(benchmark_dir / "benchmark_case_results.csv")
    unauthorized = defaultdict(int)
    for row in benchmark_cases:
        variant = row.get("system_variant", "unknown")
        try:
            unauthorized[variant] += int(row.get("unauthorized_context_count") or 0)
        except (TypeError, ValueError):
            pass

    ablation_metrics = ablation.get("metrics", []) if ablation else []
    return {
        "wp6": wp6,
        "answer_leakage": ({
            "cases": answer.get("total_cases"),
            "baseline_rate": round(float(answer.get("baseline_leakage_rate_all_cases", 0)) * 100, 1),
            "controlled_rate": round(float(answer.get("controlled_leakage_rate_all_cases", 0)) * 100, 1),
            "baseline_denied_rate": round(float(answer.get("baseline_denied_case_leakage_rate", 0)) * 100, 1),
            "controlled_denied_rate": round(float(answer.get("controlled_denied_case_leakage_rate", 0)) * 100, 1),
            "detector": answer.get("leak_detection_method", ""),
            "run_id": answer.get("run_id_utc"),
        } if answer else None),
        "prompt_injection": ({
            "cases_per_run": injection.get("case_count"),
            "baseline_asr": round(float(injection.get("baseline_total_asr", 0)) * 100, 1),
            "controlled_asr": round(float(injection.get("controlled_total_asr", 0)) * 100, 1),
            "run_id": injection.get("run_id_utc"),
            "groups": [{"name": k, "count": v.get("case_count"),
                        "baseline": round(float(v.get("baseline_asr", 0)) * 100, 1),
                        "controlled": round(float(v.get("controlled_asr", 0)) * 100, 1)}
                       for k, v in (injection.get("groups") or {}).items()],
        } if injection else None),
        "ablation": ({
            "repeats": ablation.get("repeats"),
            "cases_per_configuration_per_repeat": ablation.get("cases_per_configuration_per_repeat"),
            "metrics": [{
                "configuration": r.get("configuration"),
                "case_runs": r.get("cases"),
                "target_retrieval_leaks": r.get("target_retrieval_leaks"),
                "leaked_facts": r.get("leaked_fact_count"),
                "redact_count": r.get("redact_count"),
                "mean_latency_ms": r.get("mean_latency_ms"),
            } for r in ablation_metrics],
        } if ablation else None),
        "benchmark": {
            "datasets": datasets,
            "total_documents": sum(r["documents"] for r in datasets),
            "total_chunks": sum(r["chunks"] for r in datasets),
            "mean_latency_ms": latency,
            "unauthorized_chunk_occurrences": dict(unauthorized),
            "run_count": len(_read_csv(benchmark_dir / "benchmark_runs.csv")),
        },
        "artifact_status": {
            "answer_leakage": bool(answer), "prompt_injection": bool(injection),
            "ablation": bool(ablation), "benchmark": bool(dataset_rows and perf_rows),
        },
    }


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "RAGDemo/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Request paths/status only; credentials, OTPs, tokens and query bodies are never logged.
        super().log_message(fmt, *args)

    def _headers(self, status=200, content_type="application/json; charset=utf-8", length=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def _send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._headers(status, length=len(payload))
        self.wfile.write(payload)

    def _read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Content-Length không hợp lệ.")
        if size < 0 or size > MAX_BODY:
            raise ValueError("Dữ liệu gửi lên vượt giới hạn.")
        raw = self.rfile.read(size)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("JSON không hợp lệ.")
        if not isinstance(data, dict):
            raise ValueError("Request body phải là JSON object.")
        return data

    def _bearer(self):
        value = self.headers.get("Authorization", "")
        if value.startswith("Bearer "):
            return value[7:].strip()
        return ""

    def _require_user(self):
        from auth import AuthenticationError
        try:
            user = _verify_user(self._bearer())
        except (PermissionError, AuthenticationError, RuntimeError):
            self._send_json({"error": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại."}, 401)
            return None
        return user

    def do_HEAD(self):
        path = urlparse(self.path).path
        files = {"/": (WEB_ROOT / "index.html", "text/html; charset=utf-8"),
                 "/index.html": (WEB_ROOT / "index.html", "text/html; charset=utf-8"),
                 "/styles.css": (WEB_ROOT / "styles.css", "text/css; charset=utf-8"),
                 "/app.js": (WEB_ROOT / "app.js", "application/javascript; charset=utf-8"),
                 "/trace-details.css": (WEB_ROOT / "trace-details.css", "text/css; charset=utf-8")}
        if path not in files:
            return self._send_json({"error": "Not found"}, 404)
        target, ctype = files[path]
        try:
            size = target.stat().st_size
        except OSError:
            return self._send_json({"error": "Thiếu file giao diện demo."}, 500)
        self._headers(200, ctype, size)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._health()
        if path == "/" or path in {"/index.html", "/styles.css", "/app.js", "/trace-details.css"}:
            return self._static(path)
        if path == "/api/me":
            user = self._require_user()
            if user is not None:
                return self._send_json({"user": _user_payload(user)})
            return
        if path in {"/api/overview", "/api/documents", "/api/audit", "/api/experiments"}:
            user = self._require_user()
            if user is None:
                return
            try:
                if path == "/api/overview":
                    return self._overview(user)
                if path == "/api/documents":
                    return self._documents(user)
                if path == "/api/audit":
                    return self._audit(user)
                if path == "/api/experiments":
                    return self._send_json(_experiment_summary())
            except Exception as exc:
                self._send_json({"error": "Không thể tải dữ liệu demo.", "type": type(exc).__name__}, 503)
                return
        self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read_json()
        except ValueError as exc:
            return self._send_json({"error": str(exc)}, 400)
        if path == "/api/login":
            return self._login(data)
        if path == "/api/chat":
            user = self._require_user()
            if user is None:
                return
            return self._chat(user, data)
        self._send_json({"error": "Not found"}, 404)

    def _static(self, path):
        files = {"/": (WEB_ROOT / "index.html", "text/html; charset=utf-8"),
                 "/index.html": (WEB_ROOT / "index.html", "text/html; charset=utf-8"),
                 "/styles.css": (WEB_ROOT / "styles.css", "text/css; charset=utf-8"),
                 "/app.js": (WEB_ROOT / "app.js", "application/javascript; charset=utf-8"),
                 "/trace-details.css": (WEB_ROOT / "trace-details.css", "text/css; charset=utf-8")}
        target, ctype = files[path]
        try:
            payload = target.read_bytes()
        except OSError:
            return self._send_json({"error": "Thiếu file giao diện demo."}, 500)
        self._headers(200, ctype, len(payload))
        self.wfile.write(payload)

    def _health(self):
        db = {"ok": False, "name": None, "documents": 0, "chunks": 0, "fixture_users_ready": False}
        ollama = {"ok": False, "llm_model": False, "embedding_model": False}
        try:
            with _db_session() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database()")
                    db["name"] = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM documents")
                    db["documents"] = int(cur.fetchone()[0])
                    cur.execute("SELECT COUNT(*) FROM chunks")
                    db["chunks"] = int(cur.fetchone()[0])
                    cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
                    db["embedded_chunks"] = int(cur.fetchone()[0])
                    db["chunks_missing_embedding"] = db["chunks"] - db["embedded_chunks"]
                    cur.execute("SELECT username, mfa_secret, password_hash FROM users WHERE username = ANY(%s)", (list(FIXTURE_USERS),))
                    found = {r[0]: bool(r[1]) and str(r[2]).startswith("$2") for r in cur.fetchall()}
                    db["fixture_users_ready"] = all(found.get(name, False) for name in FIXTURE_USERS)
                    db["fixture_users_count"] = sum(1 for name in FIXTURE_USERS if found.get(name, False))
                    db["ok"] = True
        except Exception:
            pass
        try:
            import requests
            response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
            response.raise_for_status()
            names = [m.get("name", "") for m in response.json().get("models", [])]
            ollama["llm_model"] = any(n.startswith("qwen2.5:3b") for n in names)
            ollama["embedding_model"] = any(n.startswith("nomic-embed-text") for n in names)
            ollama["ok"] = True
        except Exception:
            pass
        self._send_json({"database": db, "ollama": ollama,
                         "ready": db["ok"] and db.get("chunks_missing_embedding", 1) == 0
                                  and ollama["llm_model"] and ollama["embedding_model"],
                         "note": "Kiểm tra dịch vụ và trạng thái dữ liệu demo; không thay thế kiểm thử bảo mật."})

    def _login(self, data):
        client = self.client_address[0]
        now = time.time()
        failures = _LOGIN_FAILURES[client]
        while failures and now - failures[0] > LOGIN_WINDOW_SECONDS:
            failures.popleft()
        if len(failures) >= LOGIN_MAX_FAILURES:
            return self._send_json({"error": "Quá nhiều lần đăng nhập thất bại. Hãy thử lại sau 10 phút."}, 429)
        username = str(data.get("username", "")).strip()[:80]
        password = data.get("password", "")
        otp = str(data.get("otp", "")).strip()
        if not username or not isinstance(password, str) or not password or not otp:
            return self._send_json({"error": "Vui lòng nhập username, password và mã TOTP."}, 400)
        try:
            from auth import authenticate, user_from_token, AuthenticationError
            with _db_session() as conn:
                token = authenticate(conn, username, password, otp)
                user = user_from_token(conn, token)
            failures.clear()
            return self._send_json({"token": token, "user": _user_payload(user), "expires_in": 3600})
        except Exception as exc:
            failures.append(now)
            # Avoid revealing whether username, password or MFA was incorrect.
            try:
                from auth import AuthenticationError
                if isinstance(exc, AuthenticationError):
                    return self._send_json({"error": "Thông tin đăng nhập hoặc mã TOTP không chính xác."}, 401)
            except Exception:
                pass
            return self._send_json({"error": "Không thể xác thực. Kiểm tra PostgreSQL, tài khoản fixture và cấu hình môi trường.", "type": type(exc).__name__}, 503)

    def _allowed_documents(self, conn, user):
        from pdp import decide
        with conn.cursor() as cur:
            cur.execute("""SELECT d.id, d.title, d.classification, d.department,
                                  d.protection_profile, COUNT(c.id) AS chunk_count
                           FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                           GROUP BY d.id ORDER BY d.id""")
            rows = cur.fetchall()
        allowed = []
        for row in rows:
            decision = decide(user, {"id": row[0], "classification": row[2], "department": row[3]})
            if decision.effect == "ALLOW":
                allowed.append({"id": row[0], "title": row[1], "classification": row[2],
                                "department": row[3], "protection_profile": row[4],
                                "chunks": int(row[5]), "rule_id": decision.rule_id})
        return allowed

    def _overview(self, user):
        with _db_session() as conn:
            allowed = self._allowed_documents(conn, user)
            allowed_ids = [d["id"] for d in allowed]
            chunks = sum(d["chunks"] for d in allowed)
            with conn.cursor() as cur:
                cur.execute("""SELECT stage, decision, COUNT(*)
                               FROM audit_log
                               WHERE user_id = %s AND created_at >= now() - interval '24 hours'
                               GROUP BY stage, decision""", (user["id"],))
                activity = [{"stage": r[0], "decision": r[1], "count": int(r[2])} for r in cur.fetchall()]
        by_class = defaultdict(int)
        for d in allowed:
            by_class[d["classification"]] += 1
        from controlled_rag import release_context_for_user
        release_context = release_context_for_user(user)
        return self._send_json({"user": _user_payload(user), "allowed_documents": len(allowed),
                                "allowed_chunks": chunks, "documents_by_classification": dict(by_class),
                                "audit_last_24h": activity, "release_context": release_context})

    def _documents(self, user):
        with _db_session() as conn:
            docs = self._allowed_documents(conn, user)
        self._send_json({"documents": docs, "count": len(docs)})

    def _audit(self, user):
        with _db_session() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT created_at, stage, decision, reason, rule_id, release_context
                               FROM audit_log WHERE user_id = %s
                               ORDER BY created_at DESC LIMIT 40""", (user["id"],))
                rows = cur.fetchall()
        events = [{"created_at": r[0].isoformat() if r[0] else None,
                   "stage": r[1], "decision": r[2], "reason": r[3],
                   "rule_id": r[4], "release_context": r[5]} for r in rows]
        self._send_json({"events": events, "count": len(events),
                         "note": "Giao diện không hiển thị query_text hoặc dữ kiện nhạy cảm trong audit log."})

    def _chat(self, user, data):
        query = data.get("query", "")
        if not isinstance(query, str) or not query.strip():
            return self._send_json({"error": "Hãy nhập câu hỏi trước khi gửi."}, 400)
        query = query.strip()
        if len(query) > 800:
            return self._send_json({"error": "Câu hỏi tối đa 800 ký tự."}, 400)
        token = self._bearer()
        try:
            from controlled_rag import answer_internal_query
            result = answer_internal_query(token, query, top_k=3)
        except Exception:
            return self._send_json({"error": "Không thể xử lý câu hỏi qua Controlled RAG."}, 503)

        request_id = result.get("request_id")
        doc_ids = result.get("retrieved_doc_ids") or []
        if result.get("decision") == "BLOCK" and not result.get("output_dlp_executed", False):
            return self._send_json({
                "request_id": request_id,
                "answer": result.get("answer") or "Không thể xử lý yêu cầu một cách an toàn.",
                "decision": "BLOCK",
                "output_dlp_executed": False,
                "release_context": result.get("release_context", DEFAULT_RELEASE_CONTEXT),
                "sources": [],
                "trace": [
                    {"stage": "Xác thực", "decision": "ALLOW",
                     "detail": f"Danh tính {user['username']} đã được xác thực bằng token còn hiệu lực."},
                    {"stage": "ABAC / Retrieval", "decision": "ERROR",
                     "detail": "Pipeline không hoàn tất retrieval; hệ thống dừng an toàn và không phát hành nội dung."},
                    {"stage": "Output DLP", "decision": "NOT_RUN",
                     "detail": "Output DLP chưa được gọi vì pipeline dừng trước bước sinh/phát hành câu trả lời."},
                ],
                "retrieval": {"allowed_chunks_logged": 0, "denied_candidate_occurrences": 0},
                "dlp_match_events": 0,
                "dlp_match_count": 0,
            })
        with _db_session() as conn:
            from pdp import decide
            with conn.cursor() as cur:
                cur.execute("""SELECT id, title, classification, department, protection_profile
                               FROM documents WHERE id = ANY(%s) ORDER BY id""", (doc_ids or [0],))
                sources = []
                for r in cur.fetchall():
                    resource = {"id": r[0], "classification": r[2], "department": r[3]}
                    if decide(user, resource).effect == "ALLOW":
                        sources.append({"id": r[0], "title": r[1], "classification": r[2],
                                        "department": r[3], "protection_profile": r[4]})
                cur.execute("""SELECT stage, decision, reason, rule_id, COUNT(*)
                               FROM audit_log WHERE request_id = %s
                               GROUP BY stage, decision, reason, rule_id
                               ORDER BY stage, decision""", (request_id,))
                logs = cur.fetchall()
        denied = sum(int(r[4]) for r in logs if r[0] == "retrieval" and r[1] == "DENY")
        allowed = sum(int(r[4]) for r in logs if r[0] == "retrieval" and r[1] == "ALLOW")
        dlp_rows = [r for r in logs if r[0] == "output_dlp"]
        dlp_matches = sum(int(r[4]) for r in dlp_rows if r[1] in {"REDACT", "BLOCK"})
        dlp_decision = result.get("decision", "BLOCK")
        release_context = result.get("release_context", DEFAULT_RELEASE_CONTEXT)
        dlp_executed = bool(result.get("output_dlp_executed", bool(dlp_rows)))
        dlp_trace_decision = dlp_decision if dlp_executed else "NOT_RUN"
        retrieval_decision = "ALLOW" if sources else ("DENY" if denied > 0 else "NO_RESULT")
        if dlp_decision == "NO_RESULT":
            retrieval_decision = "NO_RESULT"
        elif dlp_decision == "BLOCK" and not dlp_executed and not sources and denied == 0:
            retrieval_decision = "ERROR"
        trace = [
            {"stage": "Xác thực", "decision": "ALLOW", "detail": f"Danh tính {user['username']} đã được xác thực bằng token còn hiệu lực."},
            {"stage": "ABAC / Retrieval",
             "decision": retrieval_decision,
             "detail": (f"{len(sources)} tài liệu trong Top-K sau lọc ABAC; {denied} lượt ứng viên trái quyền bị loại khỏi đường sinh câu trả lời."
                        if sources or denied else "Không tìm thấy chunk phù hợp trong phạm vi truy cập; đây không phải quyết định từ chối quyền.")},
            {"stage": "Output DLP", "decision": dlp_trace_decision,
             "detail": (f"Ngữ cảnh phát hành do backend xác định: {release_context}. Số bản ghi match được audit: {dlp_matches}."
                        if dlp_executed else "Output DLP không được gọi vì không có kết quả retrieval hoặc pipeline dừng an toàn.")},
        ]
        self._send_json({"request_id": request_id, "answer": result.get("answer") or "Không có câu trả lời được phép phát hành.",
                         "decision": dlp_decision, "output_dlp_executed": dlp_executed, "release_context": release_context,
                         "sources": sources, "trace": trace,
                         "retrieval": {"allowed_chunks_logged": allowed, "denied_candidate_occurrences": denied},
                         "dlp_match_events": dlp_matches,
                         "dlp_match_count": result.get("dlp_match_count", dlp_matches),
                         "note": "Release context ảnh hưởng quyết định Output DLP; phạm vi tài liệu vẫn do ABAC/PDP quyết định."})


def main():
    from db_config import get_db_config
    # Validate required settings before opening the listener; no credentials are printed.
    _db_config()
    server = ThreadingHTTPServer((HOST, PORT), DemoHandler)
    print(f"RAG Demo UI đang chạy tại http://{HOST}:{PORT}")
    print("Chỉ lắng nghe trên máy local. Nhấn Ctrl+C để dừng.")
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\nĐã dừng RAG Demo UI.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
