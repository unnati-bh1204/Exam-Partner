from unittest.mock import patch

from app.documents import create_document, list_documents, mark_document, process_document


def test_create_document_starts_as_processing(db):
    doc = create_document(db, "user-1", "subject-1", "physics.pdf")
    assert doc["status"] == "processing"
    assert doc["error"] is None


def test_list_documents_scoped_to_user_and_subject(db):
    create_document(db, "user-1", "subject-1", "a.pdf")
    create_document(db, "user-1", "subject-2", "b.pdf")
    create_document(db, "user-2", "subject-1", "c.pdf")
    docs = list_documents(db, "user-1", "subject-1")
    assert len(docs) == 1
    assert docs[0]["filename"] == "a.pdf"


def test_mark_document_updates_status_and_error(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    mark_document(db, doc["_id"], "failed", "No readable text found")
    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "failed"
    assert updated["error"] == "No readable text found"


def test_process_document_marks_ready_on_success(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    with (
        patch("app.documents.extract_text", return_value=[("page 1", "some text")]),
        patch("app.documents.chunk_pages", return_value=[{"chunk_id": "c1", "text": "some text",
                                                             "filename": "a.pdf", "source_label": "page 1"}]),
        patch("app.documents.store_chunks") as mock_store,
    ):
        process_document(db, "user-1", "subject-1", doc["_id"], "/fake/path.pdf", "application/pdf", "a.pdf")

    mock_store.assert_called_once()
    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "ready"


def test_process_document_marks_failed_when_no_text_found(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    with patch("app.documents.extract_text", return_value=[]):
        process_document(db, "user-1", "subject-1", doc["_id"], "/fake/path.pdf", "application/pdf", "a.pdf")

    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "failed"
    assert "No readable text" in updated["error"]


def test_process_document_marks_failed_after_retries_exhausted(db):
    doc = create_document(db, "user-1", "subject-1", "a.pdf")
    with patch("app.documents.extract_text", side_effect=RuntimeError("Gemini unavailable")):
        process_document(db, "user-1", "subject-1", doc["_id"], "/fake/path.pdf", "application/pdf", "a.pdf")

    updated = list_documents(db, "user-1", "subject-1")[0]
    assert updated["status"] == "failed"
    assert updated["error"] == "Gemini unavailable"
