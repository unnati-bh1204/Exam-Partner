from pymongo.operations import SearchIndexModel

from app.db import chunks_collection, get_db
from app.vectorstore import INDEX_NAME


def main():
    db = get_db()
    if "chunks" not in db.list_collection_names():
        db.create_collection("chunks")
    collection = chunks_collection(db)
    index_model = SearchIndexModel(
        definition={
            "fields": [
                {"type": "vector", "path": "embedding", "numDimensions": 768, "similarity": "cosine"},
                {"type": "filter", "path": "user_id"},
                {"type": "filter", "path": "subject_id"},
            ]
        },
        name=INDEX_NAME,
        type="vectorSearch",
    )
    collection.create_search_index(model=index_model)
    print(f"Created search index '{INDEX_NAME}' on {collection.full_name}")


if __name__ == "__main__":
    main()
