
from unittest.mock import Mock, patch
import sys
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app.llm import generate_answer


def test_generate_answer_uses_deterministic_options():
    retrieved_chunks = [
        (1, 1, "Tài liệu thử nghiệm", "Nội bộ", None, "Nội dung thử nghiệm")
    ]

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": "Câu trả lời thử nghiệm"}

    with patch("app.llm.requests.post", return_value=mock_response) as mock_post:
        result = generate_answer("Câu hỏi thử nghiệm", retrieved_chunks)

    payload = mock_post.call_args.kwargs["json"]

    assert payload["options"] == {
        "temperature": 0,
        "seed": 42,
    }
    assert result == "Câu trả lời thử nghiệm"



def test_mixed_indonesian_answer_is_repaired():
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {
        "response": "Công ty ABC ra mắt pada quý 3/2026, yang mendukung usaha kecil."
    }
    repaired = Mock()
    repaired.raise_for_status.return_value = None
    repaired.json.return_value = {
        "response": "Công ty ABC dự kiến ra mắt sản phẩm vào quý III/2026."
    }
    chunks = [
        (1, 1, "Thông báo ra mắt sản phẩm", "Công khai", None,
         "Công ty ABC dự kiến ra mắt sản phẩm vào quý III/2026.")
    ]
    with patch("app.llm.requests.post", side_effect=[first, repaired]) as mock_post:
        result = generate_answer("Công ty ABC ra mắt sản phẩm khi nào?", chunks)
    assert "pada" not in result
    assert "yang" not in result
    assert mock_post.call_count == 2



def test_mixed_language_after_repair_returns_safe_fallback():
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {
        "response": "Câu trả lời có pada và yang mendukung usaha."
    }
    second = Mock()
    second.raise_for_status.return_value = None
    second.json.return_value = {
        "response": "Vẫn còn pada và yang mendukung usaha."
    }
    chunks = [
        (1, 1, "Tài liệu thử nghiệm", "Nội bộ", None, "Nội dung thử nghiệm")
    ]
    with patch("app.llm.requests.post", side_effect=[first, second]) as mock_post:
        result = generate_answer("Câu hỏi thử nghiệm", chunks)
    assert result.startswith("Mô hình chưa tạo được câu trả lời tiếng Việt")
    assert mock_post.call_count == 2



def test_observed_indonesian_no_information_answer_is_detected_and_repaired():
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {
        "response": "Mohai tidak memiliki informasi tentang tuyển dụng Data Engineering dalam tài liệu."
    }
    repaired = Mock()
    repaired.raise_for_status.return_value = None
    repaired.json.return_value = {
        "response": "Tài liệu được cung cấp chưa có thông tin cụ thể về tuyển dụng Data Engineering."
    }
    chunks = [
        (1, 1, "Hồ sơ benchmark", "Công khai", None,
         "Hồ sơ chỉ nêu trạng thái hệ thống và nhóm phụ trách.")
    ]
    with patch("app.llm.requests.post", side_effect=[first, repaired]) as mock_post:
        result = generate_answer("Thông tin tuyển dụng Data Engineering?", chunks)

    assert "tidak" not in result.casefold()
    assert "memiliki" not in result.casefold()
    assert "tuyển dụng Data Engineering" in result
    assert mock_post.call_count == 2



def test_chinese_script_answer_is_detected_and_repaired():
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {
        "response": "Hồ sơ này đang处理关于监控服务的内容。"
    }
    repaired = Mock()
    repaired.raise_for_status.return_value = None
    repaired.json.return_value = {
        "response": "Hồ sơ này nói về nội dung giám sát dịch vụ."
    }
    chunks = [
        (1, 1, "Access Service — Giám sát dịch vụ — hồ sơ 00006",
         "Nội bộ", "Kỹ thuật", "Nội dung về giám sát dịch vụ.")
    ]
    with patch("app.llm.requests.post", side_effect=[first, repaired]) as mock_post:
        result = generate_answer("Thông tin hồ sơ 00006", chunks)

    assert result == "Hồ sơ này nói về nội dung giám sát dịch vụ."
    assert mock_post.call_count == 2


def test_chinese_script_after_repair_returns_safe_vietnamese_fallback():
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {"response": "内容是关于监控服务。"}
    second = Mock()
    second.raise_for_status.return_value = None
    second.json.return_value = {"response": "仍然是中文内容。"}
    chunks = [
        (1, 1, "Tài liệu thử nghiệm", "Nội bộ", "Kỹ thuật", "Nội dung thử nghiệm")
    ]
    with patch("app.llm.requests.post", side_effect=[first, second]) as mock_post:
        result = generate_answer("Câu hỏi thử nghiệm", chunks)

    assert result.startswith("Mô hình chưa tạo được câu trả lời tiếng Việt")
    assert mock_post.call_count == 2



def test_false_no_result_for_found_record_uses_grounded_extractive_fallback():
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {
        "response": "Tôi không tìm thấy thông tin về hồ sơ 00006."
    }
    repaired = Mock()
    repaired.raise_for_status.return_value = None
    repaired.json.return_value = {
        "response": "Tôi vẫn không tìm thấy thông tin về hồ sơ 00006."
    }
    chunks = [
        (1, 6, "Access Service — Giám sát dịch vụ — hồ sơ 00006",
         "Nội bộ", "Kỹ thuật",
         "Hồ sơ DOC-1000-00006: Access Service đang giám sát dịch vụ. "
         "Nhóm phụ trách là an toàn thông tin; trạng thái hiện tại: đang triển khai.",
         0.9, "GENERAL_INTERNAL")
    ]
    with patch("app.llm.requests.post", side_effect=[first, repaired]) as mock_post:
        result = generate_answer("Tìm thông tin về hồ sơ 00006", chunks)

    assert result.startswith("Tìm thấy tài liệu khớp mã hồ sơ 00006.")
    assert "Access Service — Giám sát dịch vụ — hồ sơ 00006" in result
    assert "đang giám sát dịch vụ" in result
    assert mock_post.call_count == 2
