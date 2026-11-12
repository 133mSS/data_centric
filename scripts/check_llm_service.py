"""Smoke test thủ công cho LLM service Ollama.

Chạy từ thư mục gốc project:
    python .\\scripts\\test_llm.py

Script này xác nhận model trả về phản hồi; không phải pytest test.
"""
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"
TIMEOUT_SECONDS = 120
PROMPT = "Giải thích ngắn gọn RAG là gì."


def main():
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": PROMPT,
                "stream": False,
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(
            f"LLM request thất bại: {exc}\n"
            "Hãy kiểm tra Ollama đang chạy và model đã được tải."
        ) from exc

    try:
        data = response.json()
        answer = data["response"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(
            "Response từ Ollama không có trường 'response' hợp lệ."
        ) from exc

    if not isinstance(answer, str) or not answer.strip():
        raise SystemExit("LLM trả về câu trả lời rỗng.")

    print("LLM service: OK")
    print(f"Model: {MODEL}")
    print("\nResponse:")
    print(answer.strip())


if __name__ == "__main__":
    main()
