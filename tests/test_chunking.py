from app.chunking import chunk_pages


def test_chunk_pages_produces_unique_chunk_ids():
    pages = [("page 1", "A" * 2000)]
    chunks = chunk_pages(pages, "textbook.pdf")
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    assert len(chunks) > 1  # 2000 chars should split into multiple chunks


def test_chunk_pages_preserves_source_label_and_filename():
    pages = [("page 5", "Short text")]
    chunks = chunk_pages(pages, "notes.docx")
    assert chunks[0]["source_label"] == "page 5"
    assert chunks[0]["filename"] == "notes.docx"
    assert chunks[0]["text"] == "Short text"


def test_chunk_pages_handles_multiple_pages():
    pages = [("page 1", "First page text"), ("page 2", "Second page text")]
    chunks = chunk_pages(pages, "book.pdf")
    labels = {c["source_label"] for c in chunks}
    assert labels == {"page 1", "page 2"}
