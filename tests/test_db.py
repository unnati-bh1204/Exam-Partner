import mongomock

from app.db import users_collection


def test_users_collection_is_named_users():
    db = mongomock.MongoClient()["test_db"]
    collection = users_collection(db)
    assert collection.name == "users"
