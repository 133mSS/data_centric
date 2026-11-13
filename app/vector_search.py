import psycopg2
import requests
import threading
import re

from retrieval import get_allowed_document_ids
from pep import enforce_access


OLLAMA_URL = "http://localhost:11434/api/embeddings"

# Per-thread audit metadata keeps the legacy vector_search() API compatible.
_audit_state = threading.local()

def get_last_denied_shadow_chunks():
    return getattr(_audit_state, "denied_shadow_chunks", [])

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


def vector_search_with_audit(conn, user, query, top_k=3):
    """
    Return (authorized_chunks, denied_shadow_chunks).

    The shadow query ranks all embedded chunks but its rows are returned only
    for audit. They must never be passed to the LLM or source_documents.
    Both searches use the same query embedding and top_k.
    """
    allowed_document_ids = get_allowed_document_ids(conn, user)
    query_embedding = create_query_embedding(query)
    query_vector = "[" + ",".join(
        str(value) for value in query_embedding
    ) + "]"

    # Shadow baseline: unfiltered top-k. Metadata/content stay inside this
    # function and are used only to identify denied document/chunk IDs.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id AS chunk_id, c.document_id,
                   d.classification, d.department
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vector, top_k),
        )
        baseline_chunks = cur.fetchall()

    denied_shadow_chunks = []
    for row in baseline_chunks:
        document = {
            "id": row[1],
            "classification": row[2],
            "department": row[3],
        }
        if enforce_access(user, document).effect != "ALLOW":
            # Keep only IDs and policy metadata; do not expose this row
            # to the generation path.
            denied_shadow_chunks.append({
                "chunk_id": row[0],
                "document_id": row[1],
                "classification": row[2],
                "department": row[3],
            })

    if not allowed_document_ids:
        return [], denied_shadow_chunks

    # Controlled retrieval remains ACL-filtered before ranking. Fetch a bounded
    # candidate pool, then rerank it with title/query lexical relevance.
    # ABAC is applied in SQL before candidate generation; this never broadens access.
    # Use a wider, still bounded vector candidate pool so title-aware reranking
    # has a realistic chance to recover exact-document questions.
    candidate_k = min(max(top_k * 10, 50), 100)
    candidate_sql = """
        SELECT c.id AS chunk_id, c.document_id, d.title,
               d.classification, d.department, c.content,
               1 - (c.embedding <=> %s::vector) AS similarity,
               d.protection_profile
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.document_id = ANY(%s)
          AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(
            candidate_sql,
            (query_vector, allowed_document_ids, query_vector, candidate_k),
        )
        vector_candidates = cur.fetchall()

    def _terms(value):
        # Vietnamese diacritics are preserved; ignore very short tokens.
        return {
            token for token in re.findall(r"[0-9A-Za-zÀ-ỹ_]+", (value or "").casefold())
            if len(token) >= 2
        }

    def _strip_vietnamese_diacritics(value):
        import unicodedata
        decomposed = unicodedata.normalize("NFD", (value or "").casefold())
        return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").replace("đ", "d")

    # Remove request filler before comparing query terms with document titles.
    # Keep the original token spelling for PostgreSQL substring matching so
    # Vietnamese diacritics are respected by ILIKE/POSITION.
    stopwords = {
        "cho", "toi", "thong", "tin", "ve", "so", "ho", "tai", "lieu",
        "duoc", "cung", "cap", "nhu", "the", "nao", "la", "gi", "cua",
        "va", "trong", "mot", "cac", "nhung", "hay", "giup", "biet",
        "tim", "tra", "cuu", "kiem", "vui", "long", "ban", "theo",
    }
    query_terms = _terms(query)
    title_search_terms = sorted({
        term for term in query_terms
        if _strip_vietnamese_diacritics(term) not in stopwords
        and not re.fullmatch(r"\d{5,}", term)
    })

    # Supplement vector candidates with a parameterized, ACL-filtered title
    # lookup. This is important for explicit document IDs/titles, which may be
    # absent from the first approximate-nearest-neighbour window. It never
    # searches outside the allow-list returned by PDP.
    reference_ids = re.findall(r"(?<!\d)\d{5,}(?!\d)", query)
    title_candidates = []
    if reference_ids:
        # A record number is an identifier, not just another semantic token.
        # Search it independently from natural-language filler ("tìm", "thông tin",
        # "về", "hồ sơ"), and do not require every query word to occur in the title.
        reference_conditions = " OR ".join(
            ["POSITION(%s IN d.title) > 0"] * len(reference_ids)
        )
        title_sql = f"""
            SELECT c.id AS chunk_id, c.document_id, d.title,
                   d.classification, d.department, c.content,
                   1 - (c.embedding <=> %s::vector) AS similarity,
                   d.protection_profile
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.document_id = ANY(%s)
              AND c.embedding IS NOT NULL
              AND ({reference_conditions})
            ORDER BY c.document_id, c.id
            LIMIT %s
        """
        with conn.cursor() as cur:
            cur.execute(
                title_sql,
                (query_vector, allowed_document_ids, *reference_ids, max(candidate_k, 100)),
            )
            title_candidates = cur.fetchall()

    # An explicit record number is a hard retrieval constraint. Never fall
    # back to semantically similar but differently numbered records.
    if reference_ids:
        if not title_candidates:
            return [], denied_shadow_chunks
        candidates = title_candidates
    else:
        # De-duplicate chunks present in the vector candidate pool.
        candidates_by_id = {row[0]: row for row in vector_candidates}
        candidates = list(candidates_by_id.values())

    # Every candidate here is already restricted by the PDP allow-list.
    title_candidate_ids = {row[0] for row in title_candidates}

    query_terms_folded = {
        _strip_vietnamese_diacritics(t)
        for t in title_search_terms
    }
    meaningful_query_phrase = " ".join(title_search_terms)
    meaningful_query_phrase = _strip_vietnamese_diacritics(meaningful_query_phrase)
    ranked = []
    for row in candidates:
        title = str(row[2] or "")
        title_terms = _terms(title)
        title_terms_folded = {_strip_vietnamese_diacritics(t) for t in title_terms}
        overlap = len(query_terms_folded & title_terms_folded)
        title_phrase = _strip_vietnamese_diacritics(title)
        # Compare the meaningful query tokens after request filler is removed.
        exact_phrase = bool(meaningful_query_phrase) and meaningful_query_phrase in title_phrase
        title_coverage = overlap / max(1, len(query_terms_folded))
        title_coverage = min(title_coverage, 1.0)
        has_reference_id = any(reference_id in title for reference_id in reference_ids)
        # For explicit record-number lookups, lexical/title relevance must
        # dominate a noisy embedding score. ABAC was applied before this stage.
        vector_similarity = float(row[6] or 0.0)
        if reference_ids:
            lexical_boost = (
                (0.30 if exact_phrase else 0.0)
                + title_coverage * 0.40
                + (0.35 if has_reference_id else 0.0)
                + (0.45 if row[0] in title_candidate_ids else 0.0)
            )
            # When the user supplies descriptive title terms, lexical match is
            # primary; vector similarity is only a tie-breaker. A nearby vector
            # must not override an exact record title.
            primary_score = lexical_boost + vector_similarity * (
                1.0 if not title_search_terms else 0.10
            )
        else:
            lexical_boost = (0.12 if exact_phrase else 0.0) + title_coverage * 0.16
            primary_score = vector_similarity + lexical_boost
        ranked.append((primary_score, vector_similarity, row))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if reference_ids and not title_search_terms:
        # A bare repeated ID can map to several generated scales. If only one
        # allowed document has that ID, retain all its chunks for a stable,
        # complete summary. If multiple allowed documents share it, return one
        # representative chunk per document so the LLM can explain ambiguity.
        document_ids_in_rank_order = list(dict.fromkeys(item[2][1] for item in ranked))
        if len(document_ids_in_rank_order) == 1:
            authorized_chunks = [item[2] for item in ranked[:top_k]]
        else:
            authorized_chunks = []
            seen_documents = set()
            for item in ranked:
                document_id = item[2][1]
                if document_id in seen_documents:
                    continue
                seen_documents.add(document_id)
                authorized_chunks.append(item[2])
                if len(authorized_chunks) >= top_k:
                    break
    else:
        authorized_chunks = [item[2] for item in ranked[:top_k]]
    return authorized_chunks, denied_shadow_chunks


def vector_search(conn, user, query, top_k=3):
    """Backward-compatible ACL-filtered retrieval API."""
    # Clear stale audit data before starting a new search. If retrieval raises,
    # callers must not mistake the previous search's audit data for this one.
    _audit_state.denied_shadow_chunks = []

    authorized_chunks, denied_shadow_chunks = vector_search_with_audit(
        conn, user, query, top_k=top_k
    )
    _audit_state.denied_shadow_chunks = denied_shadow_chunks
    return authorized_chunks


def get_user(conn, username):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, role, department
            FROM users
            WHERE username = %s
            """,
            (username,)
        )

        row = cur.fetchone()

    if row is None:
        raise ValueError(f"User not found: {username}")

    return {
        "id": row[0],
        "username": row[1],
        "role": row[2],
        "department": row[3],
    }


if __name__ == "__main__":
    conn = psycopg2.connect(**get_db_config())

    try:
        usernames = [
            "nv_dev",
            "mgr_tech",
            "mgr_sales",
            "ceo_boss",
            "partner_01",
        ]

        query = "Kế hoạch sáp nhập với công ty XYZ là gì?"

        for username in usernames:
            user = get_user(conn, username)

            print(f"\n===== {username} =====")

            results = vector_search(
                conn,
                user,
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