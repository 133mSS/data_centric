"""Convert ACL-filtered retrieval chunks into DLP source documents."""


def chunks_to_source_documents(chunks):
    """Combine chunks by document ID before extracting protected facts.

    Retrieval must already have enforced ABAC. This helper only combines
    authorized chunk text; it does not grant access or query additional data.
    Expected retrieval row layout: row[1] is document_id, row[5] is chunk text.
    """
    documents_by_id = {}
    ordered_ids = []

    for index, row in enumerate(chunks):
        if not isinstance(row, (tuple, list)) or len(row) <= 5:
            raise ValueError(f"Invalid retrieval row at index {index}")

        document_id = row[1]
        text = row[5]

        if isinstance(document_id, bool) or not isinstance(document_id, int):
            raise ValueError(f"Invalid document_id at retrieval row {index}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Invalid chunk text at retrieval row {index}")

        # Retrieval SQL may append trusted documents.protection_profile at row[7].
        # Keep compatibility with legacy six/seven-column test fixtures.
        profile_name = row[7] if len(row) > 7 else None
        if profile_name is not None and not isinstance(profile_name, str):
            raise ValueError(f"Invalid protection_profile at retrieval row {index}")

        if document_id not in documents_by_id:
            documents_by_id[document_id] = {
                "document_id": document_id,
                "text": text,
            }
            if profile_name is not None:
                documents_by_id[document_id]["protection_profile"] = profile_name
            ordered_ids.append(document_id)
        else:
            existing_profile = documents_by_id[document_id].get("protection_profile")
            if profile_name is not None and existing_profile not in (None, profile_name):
                raise ValueError(f"Conflicting protection_profile for document_id={document_id}")
            if profile_name is not None:
                documents_by_id[document_id]["protection_profile"] = profile_name
            documents_by_id[document_id]["text"] += text

    return [documents_by_id[document_id] for document_id in ordered_ids]
