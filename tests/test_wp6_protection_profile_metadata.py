from pathlib import Path
import sys

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pytest
from protection_profile import get_document_profile
from source_documents import chunks_to_source_documents
from output_dlp import process_output_safely


def test_metadata_profile_is_authoritative_for_unseen_document_id():
    assert get_document_profile(6006, "GENERAL_INTERNAL") == "GENERAL_INTERNAL"


def test_unknown_metadata_profile_is_rejected_fail_closed():
    with pytest.raises(ValueError, match="Unknown protection profile"):
        get_document_profile(6006, "NOT_A_PROFILE")


def test_retrieval_metadata_flows_to_source_documents():
    rows = [(1, 6006, "Benchmark title", "Nội bộ", None, "Nội dung", 0.9, "GENERAL_INTERNAL")]
    assert chunks_to_source_documents(rows) == [{
        "document_id": 6006,
        "text": "Nội dung",
        "protection_profile": "GENERAL_INTERNAL",
    }]


def test_dlp_processes_unseen_id_when_profile_metadata_is_present():
    result = process_output_safely(
        answer="Tóm tắt thông tin chung của tài liệu.",
        source_documents=[{
            "document_id": 6006,
            "text": "Tài liệu benchmark về quy trình thông thường.",
            "protection_profile": "GENERAL_INTERNAL",
        }],
        release_context="SHARE_SUMMARY",
    )
    assert result["decision"] in {"ALLOW", "REDACT"}
    assert result["answer"] is not None
