import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_pages(pages: list[tuple[str, str]], filename: str) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = []
    for source_label, text in pages:
        for piece in splitter.split_text(text):
            chunks.append(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "text": piece,
                    "filename": filename,
                    "source_label": source_label,
                }
            )
    return chunks
