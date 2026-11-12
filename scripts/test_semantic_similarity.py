"""Thí nghiệm khám phá cosine similarity bằng embedding của Ollama.

Chạy từ thư mục gốc project:
    python .\\scripts\\test_semantic_similarity.py

Lưu ý:
- Đây là thí nghiệm quan sát điểm similarity, không phải kiểm thử bảo mật.
- Không đặt ngưỡng ALLOW/BLOCK chỉ dựa trên các kết quả này.
- Cần đánh giá trên bộ dữ liệu có nhãn trước khi dùng similarity trong policy.
"""
import requests
import numpy as np

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL = "nomic-embed-text"
TIMEOUT_SECONDS = 120

SENSITIVE_FACT = "45 triệu USD"
TEST_TEXTS = [
    ("EXACT", "45 triệu USD"),
    ("PARAPHRASE", "45 triệu đô la Mỹ"),
    ("DIFFERENT_VALUE", "12 triệu USD"),
    ("UNRELATED", "Thông báo bảo trì hệ thống"),
]


def create_embedding(text):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": text},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        vector = data["embedding"]
    except requests.RequestException as exc:
        raise RuntimeError(f"Không gọi được embedding service: {exc}") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Response embedding không hợp lệ.") from exc

    embedding = np.asarray(vector, dtype=float)
    if embedding.ndim != 1 or embedding.size == 0:
        raise RuntimeError("Embedding phải là vector một chiều không rỗng.")
    if not np.all(np.isfinite(embedding)):
        raise RuntimeError("Embedding chứa NaN hoặc giá trị vô hạn.")
    return embedding


def cosine_similarity(a, b):
    if a.shape != b.shape:
        raise ValueError(
            f"Kích thước embedding không khớp: {a.shape} và {b.shape}"
        )

    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        raise ValueError("Không thể tính cosine similarity với vector zero.")

    return float(np.dot(a, b) / denominator)


def main():
    fact_embedding = create_embedding(SENSITIVE_FACT)

    print("=" * 70)
    print("SEMANTIC SIMILARITY EXPERIMENT")
    print("=" * 70)
    print(f"Model: {MODEL}")
    print(f"Sensitive fact: {SENSITIVE_FACT}")
    print("\nScores are exploratory; no security threshold is applied.")

    for label, text in TEST_TEXTS:
        text_embedding = create_embedding(text)
        similarity = cosine_similarity(fact_embedding, text_embedding)
        print(f"\n{label}")
        print(f"Text: {text}")
        print(f"Cosine similarity: {similarity:.6f}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"Semantic similarity experiment thất bại: {exc}") from exc
