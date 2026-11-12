import psycopg2
import requests


OLLAMA_URL = "http://localhost:11434/api/embeddings"

from db_config import get_db_config


def create_query_embedding(query):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "nomic-embed-text",
            "prompt": query,
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


def baseline_vector_search(conn, query, top_k=3):
    # 1. Tạo embedding cho query
    query_embedding = create_query_embedding(query)

    query_vector = "[" + ",".join(
        str(value) for value in query_embedding
    ) + "]"

    # 2. Search trên TOÀN BỘ chunks
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id,
                d.title,
                d.classification,
                d.department,
                c.content,
                1 - (c.embedding <=> %s::vector)
                    AS similarity,
                d.protection_profile
            FROM chunks c
            JOIN documents d
                ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (
                query_vector,
                query_vector,
                top_k,
            )
        )

        return cur.fetchall()


if __name__ == "__main__":
    conn = psycopg2.connect(**get_db_config())

    try:
        query = "Kế hoạch sáp nhập với công ty XYZ là gì?"

        results = baseline_vector_search(
            conn,
            query,
            top_k=3,
        )

        for row in results:
            chunk_id = row[0]
            document_id = row[1]
            title = row[2]
            classification = row[3]
            similarity = row[6]

            print(
                f"Doc #{document_id} | "
                f"{title} | "
                f"{classification} | "
                f"similarity={similarity:.4f}"
            )

    finally:
        conn.close()