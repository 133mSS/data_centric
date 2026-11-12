SELECT
    qc.case_key,
    qc.test_category,
    qc.username,
    qc.expected_relevant_document_ids,
    d.id AS target_document_id,
    d.title,
    d.classification,
    d.department,
    qc.protected_facts
FROM benchmark_query_cases qc
LEFT JOIN documents d
    ON d.id = ANY(qc.expected_relevant_document_ids)
WHERE qc.case_key LIKE 'S%'
ORDER BY qc.case_key, d.id;
