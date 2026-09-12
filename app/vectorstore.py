from langchain_core.documents import Document
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo.database import Database

from app.db import chunks_collection
from app.embeddings import get_embeddings
from app.retry import with_retries

INDEX_NAME = "vector_index"


def get_vectorstore(db: Database) -> MongoDBAtlasVectorSearch:
    return MongoDBAtlasVectorSearch(
        collection=chunks_collection(db),
        embedding=get_embeddings(),
        index_name=INDEX_NAME,
        text_key="text",
        embedding_key="embedding",
    )


def store_chunks(db: Database, user_id: str, subject_id: str, document_id: str, chunks: list[dict]) -> None:
    vectorstore = get_vectorstore(db)
    docs = [
        Document(
            page_content=chunk["text"],
            metadata={
                "chunk_id": chunk["chunk_id"],
                "user_id": user_id,
                "subject_id": subject_id,
                "document_id": document_id,
                "filename": chunk["filename"],
                "source_label": chunk["source_label"],
            },
        )
        for chunk in chunks
    ]
    with_retries(lambda: vectorstore.add_documents(docs))


def similarity_search(db: Database, user_id: str, subject_id: str, query: str, k: int = 5) -> list[Document]:
    vectorstore = get_vectorstore(db)
    return with_retries(
        lambda: vectorstore.similarity_search(
            query, k=k, pre_filter={"user_id": user_id, "subject_id": subject_id}
        )
    )
