from unittest.mock import MagicMock, patch

import pytest

from app.extraction import extract_text


def test_extract_text_dispatches_pdf(tmp_path):
    import fitz

    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Ohm's Law")
    doc.save(str(pdf_path))
    doc.close()

    pages = extract_text(str(pdf_path), "application/pdf")

    assert "Ohm" in pages[0][1]


def test_extract_text_dispatches_image_to_gemini(tmp_path):
    image_path = tmp_path / "notes.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    fake_response = MagicMock()
    fake_response.content = "F = ma"

    with patch("app.extraction.ChatGoogleGenerativeAI") as mock_llm_cls:
        mock_llm_cls.return_value.invoke.return_value = fake_response
        pages = extract_text(str(image_path), "image/jpeg")

    assert pages == [("scanned page", "F = ma")]


def test_extract_text_retries_gemini_call_on_transient_error(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    image_path = tmp_path / "notes.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    fake_response = MagicMock()
    fake_response.content = "F = ma"

    with patch("app.extraction.ChatGoogleGenerativeAI") as mock_llm_cls:
        mock_llm_cls.return_value.invoke.side_effect = [RuntimeError("timeout"), fake_response]
        pages = extract_text(str(image_path), "image/jpeg")

    assert pages == [("scanned page", "F = ma")]
    assert mock_llm_cls.return_value.invoke.call_count == 2


def test_extract_text_rejects_unsupported_type(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")

    with pytest.raises(ValueError):
        extract_text(str(path), "text/plain")
