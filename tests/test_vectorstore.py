from unittest.mock import MagicMock, patch

from app.vectorstore import similarity_search, store_chunks


def test_store_chunks_builds_documents_with_full_metadata(db):
    chunks = [
        {"chunk_id": "c1", "text": "Ohm's Law: V = IR", "filename": "physics.pdf", "source_label": "page 3"},
    ]

    with patch("app.vectorstore.get_vectorstore") as mock_get_vectorstore:
        mock_store = MagicMock()
        mock_get_vectorstore.return_value = mock_store

        store_chunks(db, "user-1", "subject-1", "doc-1", chunks)

        added_docs = mock_store.add_documents.call_args[0][0]
        assert len(added_docs) == 1
        assert added_docs[0].page_content == "Ohm's Law: V = IR"
        assert added_docs[0].metadata == {
            "chunk_id": "c1",
            "user_id": "user-1",
            "subject_id": "subject-1",
            "document_id": "doc-1",
            "filename": "physics.pdf",
            "source_label": "page 3",
        }


def test_store_chunks_retries_on_transient_error(db, monkeypatch):
    monkeypatch.setattr("app.retry.time.sleep", lambda _: None)
    chunks = [{"chunk_id": "c1", "text": "text", "filename": "a.pdf", "source_label": "page 1"}]

    with patch("app.vectorstore.get_vectorstore") as mock_get_vectorstore:
        mock_store = MagicMock()
        mock_store.add_documents.side_effect = [RuntimeError("timeout"), None]
        mock_get_vectorstore.return_value = mock_store

        store_chunks(db, "user-1", "subject-1", "doc-1", chunks)

        assert mock_store.add_documents.call_count == 2


def test_similarity_search_filters_by_user_and_subject(db):
    with patch("app.vectorstore.get_vectorstore") as mock_get_vectorstore:
        mock_store = MagicMock()
        mock_store.similarity_search.return_value = []
        mock_get_vectorstore.return_value = mock_store

        similarity_search(db, "user-1", "subject-1", "What is Ohm's Law?", k=5)

        mock_store.similarity_search.assert_called_once_with(
            "What is Ohm's Law?", k=5, pre_filter={"user_id": "user-1", "subject_id": "subject-1"}
        )
