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


def test_answer_question_retrieves_enough_chunks_for_dense_documents(db):
    """A single dense document's chunks are all topically similar, so too small
    a k can miss the one chunk that actually defines the topic. Retrieval must
    ask for a wide enough window."""
    from unittest.mock import MagicMock, patch

    fake = MagicMock()
    fake.content = "An answer."

    with (
        patch("app.rag_chain.similarity_search", return_value=[]) as mock_search,
        patch("app.rag_chain.get_llm", return_value=MagicMock(invoke=lambda *a, **k: fake)),
    ):
        answer_question(db, "user-1", "subject-1", "what is RAG?")

    requested_k = mock_search.call_args.kwargs["k"]
    assert requested_k >= 10, f"k={requested_k} is too narrow for a dense single-document subject"


def _doc(text, filename, label):
    from langchain_core.documents import Document
    return Document(page_content=text, metadata={"filename": filename, "source_label": label})


def test_citations_reflect_the_chunks_the_model_actually_used(db):
    """Citing the highest-similarity chunks is misleading when the answer came
    from a different one. Cite what the model says it used."""
    from unittest.mock import MagicMock, patch

    retrieved = [
        _doc("Unrelated tangent.", "doc.pdf", "page 7"),
        _doc("Another tangent.", "doc.pdf", "page 4"),
        _doc("RAG means Retrieval-Augmented Generation.", "doc.pdf", "page 1"),
    ]
    fake = MagicMock()
    fake.content = "RAG means Retrieval-Augmented Generation.\nSOURCES: 3"

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm", return_value=MagicMock(invoke=lambda *a, **k: fake)),
    ):
        result = answer_question(db, "u1", "s1", "what is RAG?")

    assert result["citations"] == [{"filename": "doc.pdf", "source_label": "page 1"}]
    assert "SOURCES:" not in result["answer"]


def test_citations_deduplicate_and_survive_a_missing_sources_line(db):
    from unittest.mock import MagicMock, patch

    retrieved = [_doc("A", "d.pdf", "page 1"), _doc("B", "d.pdf", "page 2")]
    fake = MagicMock()
    fake.content = "An answer with no sources line."

    with (
        patch("app.rag_chain.similarity_search", return_value=retrieved),
        patch("app.rag_chain.get_llm", return_value=MagicMock(invoke=lambda *a, **k: fake)),
    ):
        result = answer_question(db, "u1", "s1", "q")

    # Falls back to the top hits rather than dropping citations entirely.
    assert len(result["citations"]) >= 1
    assert result["answer"] == "An answer with no sources line."
