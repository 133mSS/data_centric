
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
