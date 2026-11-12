import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "app"))

import requests
import psycopg2
from db_config import get_db_config

URL = "http://localhost:11434/api/embeddings"
cache = {}

def embed(text):
    if text not in cache:
        r = requests.post(
            URL,
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=120,
        )
        r.raise_for_status()
        cache[text] = r.json()["embedding"]
    return cache[text]

conn = psycopg2.connect(**get_db_config())

tests = [
    ("Có thể xem tóm tắt chính sách nghỉ phép không?", 2),
    ("Mô tả công việc kỹ sư dữ liệu gồm những gì?", 8),
]

try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.document_id, d.title, c.content
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
        """)
        docs = cur.fetchall()

    modes = {
        "plain_content": (lambda q: q, lambda t, c: c),
        "prefixed_content": (
            lambda q: "search_query: " + q,
            lambda t, c: "search_document: " + c,
        ),
        "prefixed_title_content": (
            lambda q: "search_query: " + q,
            lambda t, c: "search_document: " + t + ". " + c,
        ),
    }

    for query, target_id in tests:
        print(f"\nQUERY: {query}")

        for mode, (query_fn, doc_fn) in modes.items():
            qvec = embed(query_fn(query))
            scored = []

            for doc_id, title, content in docs:
                dvec = embed(doc_fn(title, content))
                dot = sum(a * b for a, b in zip(qvec, dvec))
                nq = sum(a * a for a in qvec) ** 0.5
                nd = sum(a * a for a in dvec) ** 0.5
                distance = 1 - dot / (nq * nd)
                scored.append((doc_id, title, distance))

            scored.sort(key=lambda x: x[2])
            rank = next(
                (i for i, row in enumerate(scored, 1)
                 if row[0] == target_id),
                None,
            )

            print(f"  {mode}: target rank={rank}")
            for i, row in enumerate(scored[:3], 1):
                print(
                    f"    {i}. doc={row[0]} "
                    f"distance={row[2]:.6f} title={row[1]}"
                )
finally:
    conn.close()
