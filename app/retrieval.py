import psycopg2

from pep import enforce_access


from db_config import get_db_config


def get_allowed_document_ids(conn, user):
    """
    Xác định các document mà user được phép truy cập.
    Policy được kiểm tra bằng policy.py.
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, classification, department
            FROM documents
            """
        )

        documents = cur.fetchall()

    allowed_ids = []

    for row in documents:
        document = {
            "id": row[0],
            "classification": row[1],
            "department": row[2],
        }

        decision = enforce_access(user, document).effect

        if decision == "ALLOW":
            allowed_ids.append(document["id"])

    return allowed_ids


def retrieve_chunks(conn, user):
    """
    Chỉ lấy chunks thuộc các document đã được policy cho phép.
    """

    allowed_document_ids = get_allowed_document_ids(conn, user)

    if not allowed_document_ids:
        return []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id,
                d.title,
                d.classification,
                d.department,
                c.content
            FROM chunks c
            JOIN documents d
                ON c.document_id = d.id
            WHERE c.document_id = ANY(%s)
            ORDER BY c.id
            """,
            (allowed_document_ids,)
        )

        rows = cur.fetchall()

    return rows