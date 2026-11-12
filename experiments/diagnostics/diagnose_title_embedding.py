import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "app"))

import requests
import psycopg2
from db_config import get_db_config

URL = "http://localhost:11434/api/embeddings"

def embed(text):
    r = requests.post(
        URL,
        json={"model": "nomic-embed-text", "prompt": text},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["embedding"]

conn = psycopg2.connect(**get_db_config())

try:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.id, c.document_id, d.title, c.content
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id IN (2, 8)
            ORDER BY c.document_id
        """)
        targets = cur.fetchall()

        for query, target_id in [
            ("Có thể xem tóm tắt chính sách nghỉ phép không?", 2),
            ("Mô tả công việc kỹ sư dữ liệu gồm những gì?", 8),
        ]:
            qvec = "[" + ",".join(map(str, embed(query))) + "]"
            print(f"\nQUERY: {query}")

            for mode in ("content_only", "title_plus_content"):
                cur.execute("""
                    SELECT c.document_id, d.title,
                           c.embedding <=> %s::vector AS distance
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.embedding IS NOT NULL
                    ORDER BY distance
                """, (qvec,))
                current_rank = cur.fetchall()

                if mode == "content_only":
                    rows = current_rank
                else:
                    # Re-embed title + content for every chunk, only in memory.
                    scored = []
                    cur.execute("""
                        SELECT c.document_id, d.title, c.content
                        FROM chunks c
                        JOIN documents d ON d.id = c.document_id
                        WHERE c.embedding IS NOT NULL
                    """)
                    all_chunks = cur.fetchall()
                    for doc_id, title, content in all_chunks:
                        v = "[" + ",".join(
                            map(str, embed(f"{title}. {content}"))
                        ) + "]"
                        cur.execute(
                            "SELECT %s::vector <=> %s::vector",
                            (qvec, v)
                        )
                        scored.append((doc_id, title, cur.fetchone()[0]))
                    rows = sorted(scored, key=lambda x: x[2])

                rank = next(
                    (i for i, row in enumerate(rows, 1)
                     if row[0] == target_id),
                    None
                )
                print(f"  {mode}: target rank={rank}")
                for i, row in enumerate(rows[:3], 1):
                    print(f"    {i}. doc={row[0]} distance={row[2]:.6f} title={row[1]}")

finally:
    conn.close()
