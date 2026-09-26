"""pymongo client and index setup. All DB access goes through get_collection()."""
import threading

from django.conf import settings
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

_client: MongoClient | None = None
_lock = threading.Lock()


def get_client() -> MongoClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = MongoClient(
                    settings.MONGO_URI,
                    tz_aware=True,
                    serverSelectionTimeoutMS=5000,
                )
    return _client


def get_db() -> Database:
    return get_client()[settings.MONGO_DB]


def get_collection(name: str) -> Collection:
    return get_db()[name]


def ensure_indexes() -> None:
    llm_calls = get_collection("llm_calls")
    llm_calls.create_index([("created_at", DESCENDING)])
    llm_calls.create_index([("app_id", ASCENDING), ("created_at", DESCENDING)])
    llm_calls.create_index([("flags.type", ASCENDING), ("created_at", DESCENDING)])
    llm_calls.create_index([("check_status", ASCENDING)])
    llm_calls.create_index([("request_id", ASCENDING)], unique=True)

    get_collection("baselines").create_index([("app_id", ASCENDING)], unique=True)
    get_collection("alerts").create_index([("acknowledged", ASCENDING), ("created_at", DESCENDING)])
