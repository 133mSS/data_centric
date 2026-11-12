
"""
Output DLP integration.

Pipeline:
1. Receive an answer and ABAC-authorized source documents.
2. Validate all inputs.
3. Select protected facts using each document's Protection Profile.
4. Match protected facts against the answer.
5. Classify the three configured generic values using per-value context signals.
6. Apply the release policy: REDACT confirmed sensitive values or BLOCK uncertain summaries.
7. Fail closed if any processing step fails.
"""

from structured_fact_extractor import extract_structured_facts
from protection_profile import (
    PROTECTION_PROFILES,
    get_document_profile,
    select_protected_facts,
    CONTEXTUAL_FACT_RULES,
)
from sensitive_fact_matcher import match_protected_facts, NORMALIZERS
from output_dlp_policy import decide_release, ReleaseContext
from redaction import (
    find_exact_matches,
    merge_matches,
    apply_redaction,
)


def _validate_inputs(
    answer: str,
    source_documents: list[dict],
    release_context: str,
) -> str:
    """Validate inputs before processing protected information."""

    # Validate answer.
    if not isinstance(answer, str):
        raise TypeError("answer must be a string")

    if not answer.strip():
        raise ValueError("answer must not be empty")

    # Validate source documents.
    if not isinstance(source_documents, list):
        raise TypeError("source_documents must be a list")

    if not source_documents:
        raise ValueError(
            "source_documents must not be empty; "
            "protected facts cannot be verified without source documents"
        )

    for index, document in enumerate(source_documents):
        if not isinstance(document, dict):
            raise TypeError(
                f"source_documents[{index}] must be a dictionary"
            )

        if "document_id" not in document:
            raise ValueError(
                f"source_documents[{index}] is missing document_id"
            )

        if "text" not in document:
            raise ValueError(
                f"source_documents[{index}] is missing text"
            )

        document_id = document["document_id"]
        source_text = document["text"]

        # bool is a subclass of int in Python, so reject it explicitly.
        if (
            isinstance(document_id, bool)
            or not isinstance(document_id, int)
        ):
            raise TypeError(
                f"source_documents[{index}].document_id "
                "must be an integer"
            )

        if not isinstance(source_text, str):
            raise TypeError(
                f"source_documents[{index}].text must be a string"
            )

        if not source_text.strip():
            raise ValueError(
                f"source_documents[{index}].text must not be empty"
            )

    # Normalize and validate the trusted release context.
    try:
        context = ReleaseContext(release_context)
    except (ValueError, TypeError):
        raise ValueError("Unsupported release_context") from None

    return context.value



def _match_configured_protection_catalog(answer: str, answer_facts: list[dict]) -> list[dict]:
    """
    Match output against every explicitly configured protected value.

    Unlike source-selected matching, this catches known secrets even when
    the authorized retrieved source does not contain them. Three explicitly
    configured generic structured values are excluded here and handled by the
    contextual classifier; all other configured catalog entries remain global.
    """
    structured_matches = []
    exact_protected_values = []

    for profile_name, profile in PROTECTION_PROFILES.items():
        for selector in profile.get("protected_facts", []):
            if selector.get("contextual"):
                continue
            fact_type = selector.get("type")
            expected_canonical = selector.get("canonical")
            expected_raw = selector.get("raw")

            normalizer = NORMALIZERS.get(fact_type)
            if expected_canonical is None and expected_raw is not None and normalizer:
                expected_canonical = normalizer(expected_raw)

            for answer_fact in answer_facts:
                if answer_fact.get("type") != fact_type:
                    continue

                matched = False
                if expected_canonical is not None:
                    matched = answer_fact.get("canonical") == expected_canonical
                elif expected_raw is not None:
                    matched = answer_fact.get("raw", "").casefold() == expected_raw.casefold()

                if matched:
                    structured_matches.append({
                        "type": fact_type,
                        "protected_value": expected_raw or expected_canonical,
                        "matched_raw": answer_fact["raw"],
                        "canonical": answer_fact.get("canonical"),
                        "start": answer_fact["start"],
                        "end": answer_fact["end"],
                        "profile": profile_name,
                    })

        for entity in profile.get("protected_entities", []):
            exact_protected_values.append({
                "type": "named_entity",
                "value": entity,
                "protected": True,
                "profile": profile_name,
            })

        for phrase in profile.get("protected_phrases", []):
            exact_protected_values.append({
                "type": "sensitive_phrase",
                "value": phrase,
                "protected": True,
                "profile": profile_name,
            })

    exact_matches = find_exact_matches(answer, exact_protected_values)
    return merge_matches(structured_matches, exact_matches)


def _contains_context_signal(text: str, signal: str) -> bool:
    """Match configured signals; standalone identifiers use token boundaries."""
    import re

    if re.fullmatch(r"[A-Za-z0-9_]+", signal):
        return re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(signal)}(?![A-Za-z0-9_])",
            text,
            flags=re.IGNORECASE,
        ) is not None
    return signal.casefold() in text.casefold()


def _classify_contextual_facts(
    answer: str,
    answer_facts: list[dict],
    source_protected_facts: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Classify configured generic structured values using explicit signals.

    Returns (sensitive_matches, uncertain_matches, classifications). BENIGN
    values are intentionally not returned as protected matches. Sensitive source
    profile evidence or a narrow sensitive signal wins over benign signals.
    """
    sensitive_matches = []
    uncertain_matches = []
    classifications = []

    for fact in answer_facts:
        canonical = fact.get("canonical")
        rule = CONTEXTUAL_FACT_RULES.get(canonical)
        if not rule or fact.get("type") != rule.get("type"):
            continue

        source_profile_evidence = any(
            item.get("canonical") == canonical
            and item.get("profile") in rule.get("sensitive_profiles", [])
            for item in source_protected_facts
        )
        sensitive_signals = [
            signal for signal in rule.get("sensitive_signals", [])
            if _contains_context_signal(answer, signal)
        ]
        benign_signals = [
            signal for signal in rule.get("benign_signals", [])
            if _contains_context_signal(answer, signal)
        ]

        if source_profile_evidence or sensitive_signals:
            status = "SENSITIVE"
            sensitive_matches.append({
                "type": fact["type"],
                "protected_value": canonical,
                "matched_raw": fact["raw"],
                "canonical": canonical,
                "start": fact["start"],
                "end": fact["end"],
                "profile": "CONTEXTUAL_CLASSIFIER",
            })
        elif benign_signals:
            status = "BENIGN"
        else:
            status = "UNCERTAIN"
            uncertain_matches.append({
                "type": fact["type"],
                "matched_raw": fact["raw"],
                "canonical": canonical,
                "start": fact["start"],
                "end": fact["end"],
            })

        classifications.append({
            "type": fact["type"],
            "canonical": canonical,
            "status": status,
            "source_profile_evidence": source_profile_evidence,
        })

    return sensitive_matches, uncertain_matches, classifications


def process_output(
    answer: str,
    source_documents: list[dict],
    release_context: str,
) -> dict:
    """
    Process an LLM answer before release.

    Each source document must contain:
        {
            "document_id": int,
            "text": str,
        }

    IMPORTANT:
    source_documents must contain only documents already authorized
    by the upstream ABAC retrieval process.

    release_context must be assigned by a trusted backend workflow.
    """

    # 0. Validate all inputs before processing.
    release_context = _validate_inputs(
        answer,
        source_documents,
        release_context,
    )

    # 1. Select protected facts from authorized source documents.
    protected_facts = []

    for document in source_documents:
        document_id = document["document_id"]
        source_text = document["text"]

        profile_name = get_document_profile(
            document_id, document.get("protection_profile")
        )
        source_facts = extract_structured_facts(source_text)

        document_protected_facts = select_protected_facts(
            profile_name,
            source_facts,
            source_text=source_text,
        )

        protected_facts.extend(document_protected_facts)

    # 2. Detect structured facts in the generated answer.
    answer_facts = extract_structured_facts(answer)

    structured_matches = match_protected_facts(
        protected_facts,
        answer_facts,
    )

    # 3. Also scan the global configured protection catalog. This is
    # independent of whether the protected value appeared in retrieved text.
    catalog_matches = _match_configured_protection_catalog(
        answer,
        answer_facts,
    )

    contextual_matches, uncertain_matches, contextual_classifications = (
        _classify_contextual_facts(answer, answer_facts, protected_facts)
    )

    # 4. Detect exact phrases and named entities from source-selected profiles.
    exact_matches = find_exact_matches(
        answer,
        protected_facts,
    )

    # 5. Merge source-based and catalog-based matches.
    matches = merge_matches(
        structured_matches,
        merge_matches(
            contextual_matches,
            merge_matches(exact_matches, catalog_matches),
        ),
    )

    # 6. Let the trusted release policy handle sensitive and uncertain facts.
    policy_result = decide_release(
        release_context,
        matches,
        uncertain_matches=uncertain_matches,
    )

    decision = policy_result["decision"]

    if decision == "REDACT":
        released_answer = apply_redaction(answer, matches)
    elif decision == "ALLOW":
        released_answer = answer
    elif decision == "BLOCK":
        released_answer = None
    else:
        # Defensive protection: unknown decisions must never release
        # the original answer.
        raise ValueError(
            f"Unsupported release decision: {decision!r}"
        )

    return {
        "release_context": policy_result["release_context"],
        "decision": decision,
        "answer": released_answer,
        "matches": matches,
        "matched_count": len(matches),
        "uncertain_count": len(uncertain_matches),
        "contextual_classifications": contextual_classifications,
    }


def process_output_safely(
    answer: str,
    source_documents: list[dict],
    release_context: str,
) -> dict:
    """
    Fail-closed wrapper.

    If Output DLP processing fails, never return the original
    answer as an approved output.
    """

    try:
        return process_output(
            answer=answer,
            source_documents=source_documents,
            release_context=release_context,
        )

    except Exception as exc:
        # Never include the original answer in the error result.
        return {
            "release_context": release_context,
            "decision": "BLOCK",
            "answer": None,
            "matches": [],
            "matched_count": 0,
            "uncertain_count": 0,
            "contextual_classifications": [],
            "error": type(exc).__name__,
        }
