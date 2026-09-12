from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.config import settings


@lru_cache
def get_client() -> MongoClient:
    return MongoClient(settings.mongodb_uri)


def get_db() -> Database:
    return get_client()[settings.mongodb_db_name]


def users_collection(db: Database) -> Collection:
    return db["users"]


def subjects_collection(db: Database) -> Collection:
    return db["subjects"]


def documents_collection(db: Database) -> Collection:
    return db["documents"]


def chunks_collection(db: Database) -> Collection:
    return db["chunks"]


def chats_collection(db: Database) -> Collection:
    return db["chats"]
