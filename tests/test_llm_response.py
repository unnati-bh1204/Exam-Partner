from unittest.mock import MagicMock

from app.llm_response import text_from_response


def test_text_from_response_handles_plain_string_content():
    response = MagicMock()
    response.content = "  Ohm's Law states V = IR.  "
    assert text_from_response(response) == "Ohm's Law states V = IR."


def test_text_from_response_handles_list_of_text_blocks():
    response = MagicMock()
    response.content = [{"type": "text", "text": "Ohm's Law states V = IR."}]
    assert text_from_response(response) == "Ohm's Law states V = IR."


def test_text_from_response_joins_multiple_text_blocks_and_skips_non_text():
    response = MagicMock()
    response.content = [
        {"type": "text", "text": "Ohm's Law "},
        {"type": "thought_signature", "extras": {"signature": "abc123"}},
        {"type": "text", "text": "states V = IR."},
    ]
    assert text_from_response(response) == "Ohm's Law states V = IR."
