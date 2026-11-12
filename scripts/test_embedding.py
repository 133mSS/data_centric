"""Smoke test thủ công cho embedding service của Ollama.

Chạy từ thư mục gốc project:
    python .\\scripts\\test_embedding.py

Script này kiểm tra kết nối và cấu trúc response; không phải pytest test.
"""
import requests

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL = "nomic-embed-text"
TIMEOUT_SECONDS = 120


def main():
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": "test embedding"},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SystemExit(
            f"Embedding request thất bại: {exc}\n"
            "Hãy kiểm tra Ollama đang chạy và model đã được tải."
        ) from exc

    try:
        data = response.json()
        vector = data["embedding"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(
            "Response từ Ollama không có cấu trúc embedding hợp lệ."
        ) from exc

    if not isinstance(vector, list) or not vector:
        raise SystemExit("Embedding rỗng hoặc không phải một list.")
    if not all(isinstance(value, (int, float)) for value in vector):
        raise SystemExit("Embedding chứa phần tử không phải số.")

    print("Embedding service: OK")
    print(f"Model: {MODEL}")
    print(f"Embedding dimension: {len(vector)}")
    print(f"First 5 values: {vector[:5]}")


if __name__ == "__main__":
    main()
