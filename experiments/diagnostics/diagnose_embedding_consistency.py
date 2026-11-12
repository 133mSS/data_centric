"""Read-only diagnostic: compare saved chunk vectors with fresh embeddings of current text."""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import requests
import psycopg2
from db_config import get_db_config

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL = "nomic-embed-text"
TARGET_DOCS = {2, 8}

def embed(text: str) -> list[float]:
    response = requests.post(OLLAMA_URL, json={"model": MODEL, "prompt": text}, timeout=120)
    response.raise_for_status()
    vector = response.json()["embedding"]
    if len(vector) != 768:
        raise ValueError(f"{MODEL} returned {len(vector)} dimensions, expected 768")
    return vector

def as_pgvector(values: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"

def main() -> int:
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            db_name, db_user = cur.fetchone()
        print(f"Database: {db_name}; DB user: {db_user}")
        print(f"Model: {MODEL}")
        print("READ-ONLY: compares stored embeddings to fresh embeddings of current chunk text")
        print("=" * 78)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.document_id, d.title, c.content,
                       c.embedding <=> c.embedding AS self_distance,
                       vector_dims(c.embedding)
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL ORDER BY c.id
            """)
            chunks = cur.fetchall()
        if not chunks:
            print("No embedded chunks found.")
            return 1
        for chunk_id, doc_id, title, content, self_distance, dims in chunks:
            if doc_id not in TARGET_DOCS:
                continue
            fresh_vector = as_pgvector(embed(content))
            with conn.cursor() as cur:
                cur.execute("SELECT embedding <=> %s::vector FROM chunks WHERE id = %s", (fresh_vector, chunk_id))
                distance = cur.fetchone()[0]
            print(f"chunk_id={chunk_id} doc_id={doc_id} dims={dims} self_distance={self_distance} stored_vs_fresh_content_distance={distance:.6f}")
            print(f"  title={title!r}")
            print(f"  content={content!r}")
        print("\nInterpretation:")
        print("- self_distance should be 0.")
        print("- stored_vs_fresh_content_distance near 0 suggests the saved vector matches current text under this model.")
        print("- A noticeably larger distance suggests stale/mismatched embeddings, a changed model/version, or different text at ingestion.")
        print("- This tests consistency, not semantic retrieval quality.")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
