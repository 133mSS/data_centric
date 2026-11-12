import requests
import psycopg2


OLLAMA_URL = "http://localhost:11434/api/embeddings"

from db_config import get_db_config


def create_embedding(text):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "nomic-embed-text",
            "prompt": text,
        },
        timeout=120,
    )

    response.raise_for_status()

    embedding = response.json()["embedding"]

    if len(embedding) != 768:
        raise ValueError(
            f"Invalid embedding dimension: {len(embedding)}"
        )

    return embedding


def generate_embeddings():
    conn = psycopg2.connect(**get_db_config())

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content
                FROM chunks
                WHERE embedding IS NULL
                ORDER BY id
                """
            )

            chunks = cur.fetchall()

        print(f"Chunks cần embedding: {len(chunks)}")

        for chunk_id, content in chunks:
            embedding = create_embedding(content)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chunks
                    SET embedding = %s
                    WHERE id = %s
                    """,
                    (embedding, chunk_id)
                )

            conn.commit()

            print(
                f"[PASS] Chunk #{chunk_id} "
                f"→ embedding dimension = {len(embedding)}"
            )

    finally:
        conn.close()


if __name__ == "__main__":
    generate_embeddings()