from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from app.rag_chain import answer_general, answer_question


def _fake_doc(text, filename, source_label):
    return Document(page_content=text, metadata={"filename": filename, "source_label": source_label})


def test_answer_question_returns_grounded_answer_with_citations(db):
    retrieved = [_fake_doc("Ohm's Law: V = IR", "physics.pdf", "page 3")]
    fake_response = MagicMock()
    fake_response.content = "Ohm's Law states that V = IR."

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm") as mock_get_llm,
    ):
        mock_get_llm.return_value.invoke.return_value = fake_response
        result = answer_question(db, "user-1", "subject-1", "What is Ohm's Law?")

    assert result["found"] is True
    assert result["response_mode"] == "rag"
    assert result["answer"] == "Ohm's Law states that V = IR."
    assert result["citations"] == [{"filename": "physics.pdf", "source_label": "page 3"}]


def test_answer_question_reports_not_found_when_llm_signals_it(db):
    retrieved = [_fake_doc("Unrelated content", "physics.pdf", "page 1")]
    fake_response = MagicMock()
    fake_response.content = "NOT_FOUND_IN_MATERIAL"

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm") as mock_get_llm,
    ):
        mock_get_llm.return_value.invoke.return_value = fake_response
        result = answer_question(db, "user-1", "subject-1", "What is quantum entanglement?")

    assert result["found"] is False
    assert result["citations"] == []
    assert "Not found" in result["answer"]


def test_answer_question_reports_not_found_when_no_chunks_retrieved(db):
    with patch("app.rag_chain.similarity_search", return_value=[]):
        result = answer_question(db, "user-1", "subject-1", "What is quantum entanglement?")

    assert result["found"] is False
    assert result["citations"] == []


def test_answer_question_retries_gemini_call_on_transient_error(db, monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    retrieved = [_fake_doc("Ohm's Law: V = IR", "physics.pdf", "page 3")]
    fake_response = MagicMock()
    fake_response.content = "Ohm's Law states that V = IR."

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm") as mock_get_llm,
    ):
        mock_get_llm.return_value.invoke.side_effect = [RuntimeError("timeout"), fake_response]
        result = answer_question(db, "user-1", "subject-1", "What is Ohm's Law?")

    assert result["found"] is True
    assert mock_get_llm.return_value.invoke.call_count == 2


def test_answer_general_has_no_citations_and_general_mode():
    fake_response = MagicMock()
    fake_response.content = "Quantum entanglement is a phenomenon where..."

    with patch("app.rag_chain.get_llm") as mock_get_llm:
        mock_get_llm.return_value.invoke.return_value = fake_response
        result = answer_general("What is quantum entanglement?")

    assert result["response_mode"] == "general"
    assert result["citations"] == []
    assert result["found"] is True
    assert "entanglement" in result["answer"]
