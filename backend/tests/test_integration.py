"""End-to-end against a real MongoDB (skipped when none is reachable).

Uses a throwaway database: <MONGO_DB>_test.
"""
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from django.conf import settings
from django.test import Client, override_settings
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from core import db


def _mongo_available() -> bool:
    try:
        MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=1000).admin.command("ping")
        return True
    except PyMongoError:
        return False


pytestmark = pytest.mark.skipif(not _mongo_available(), reason="MongoDB not reachable")

TEST_DB = f"{settings.MONGO_DB}_test"
NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def test_db():
    with override_settings(MONGO_DB=TEST_DB, LENS_API_KEY="dev-key"):
        db.get_client().drop_database(TEST_DB)
        db.ensure_indexes()
        from checks import worker
        worker._baseline_cache.clear()
        yield
        db.get_client().drop_database(TEST_DB)


def make_doc(i, *, app="bot", length=600, latency=1000, status="success", flags=(), minutes_ago=5):
    severity = max((f["severity"] for f in flags), key=["low", "medium", "high"].index, default="none")
    return {
        "request_id": f"req_{i:06x}",
        "app_id": app,
        "model": "gpt-4o-mini",
        "provider": "mock",
        "prompt": {"messages": [{"role": "user", "content": f"question {i}"}], "system": "", "char_len": 10},
        "response": {"text": "x" * length, "char_len": length, "finish_reason": "stop"},
        "expected_format": None,
        "tokens": {"prompt": 3, "completion": length // 4, "total": 3 + length // 4},
        "latency_ms": latency,
        "status": status,
        "error": None,
        "check_status": "done",
        "flags": list(flags),
        "severity": severity,
        "is_failure": severity == "high" or status != "success",
        "tags": {},
        "created_at": NOW - timedelta(minutes=minutes_ago),
    }


REFUSAL = {"type": "refusal", "severity": "medium", "detail": "x"}
ERROR = {"type": "error", "severity": "high", "detail": "boom"}


def get(path, **params):
    resp = Client().get(path, params)
    assert resp.status_code == 200, resp.content
    return resp.json()


def test_worker_processes_pending_call():
    from checks import worker
    doc = make_doc(1, length=0) | {"check_status": "pending", "flags": [], "response": {
        "text": "I'm sorry, but I can't help with that request.", "char_len": 47, "finish_reason": "stop"}}
    db.get_collection("llm_calls").insert_one(doc)
    assert worker.sweep_pending() == 1
    stored = db.get_collection("llm_calls").find_one({"request_id": doc["request_id"]})
    assert stored["check_status"] == "done"
    assert [f["type"] for f in stored["flags"]] == ["refusal"]
    assert stored["severity"] == "medium"


def test_stats_endpoints():
    calls = db.get_collection("llm_calls")
    calls.insert_many(
        [make_doc(i) for i in range(8)]
        + [make_doc(100, flags=[REFUSAL]), make_doc(101, status="provider_error", length=0, flags=[ERROR])]
        + [make_doc(200, minutes_ago=90)]  # previous window
        + [make_doc(300, app="other")]
    )

    s = get("/api/stats/summary", app_id="bot")
    assert s["total_calls"] == 10 and s["failures"] == 1 and s["flagged"] == 2
    assert s["failure_rate"] == 0.1 and s["p95_latency_ms"] == 1000
    assert s["previous"]["total_calls"] == 1 and s["deltas"]["total_calls"] == 9

    ts = get("/api/stats/timeseries", app_id="bot")
    assert ts["bucket_secs"] == 60 and len(ts["points"]) in (60, 61)
    assert sum(p["calls"] for p in ts["points"]) == 10

    fl = get("/api/stats/flags")
    assert {f["type"]: f["count"] for f in fl["flags"]} == {"refusal": 1, "error": 1}
    assert fl["flags"][0]["by_severity"] in ({"high": 1}, {"medium": 1})

    page = get("/api/calls", app_id="bot", page_size=5)
    assert page["total"] == 10 and len(page["items"]) == 5
    assert get("/api/calls", flag="refusal")["items"][0]["flags"] == ["refusal"]
    assert get("/api/calls", severity="high")["total"] == 1
    assert get("/api/calls", q="QUESTION 101")["items"][0]["request_id"] == "req_000065"

    detail = get("/api/calls/req_000064")
    assert detail["flags"][0]["type"] == "refusal" and "_id" not in detail
    assert Client().get("/api/calls/req_nope").status_code == 404

    assert {a["app_id"] for a in get("/api/apps")["apps"]} == {"bot", "other"}


def test_baseline_and_drift_alerts():
    from checks import drift
    calls = db.get_collection("llm_calls")
    # Healthy history 2-20h ago: ~600 chars, 2% refusals
    history = [make_doc(i, length=500 + (i % 5) * 50, minutes_ago=120 + i * 2,
                        flags=[REFUSAL] if i % 50 == 0 else []) for i in range(300)]
    calls.insert_many(history)

    resp = Client().post("/api/baselines/bot/rebuild", HTTP_X_LLM_LENS_KEY="dev-key")
    assert resp.status_code == 200, resp.content
    assert resp.json()["sample_size"] == 300
    assert Client().post("/api/baselines/nobody/rebuild", HTTP_X_LLM_LENS_KEY="dev-key").status_code == 422
    assert Client().post("/api/baselines/bot/rebuild").status_code == 401

    # Incident in the last hour: long answers and lots of refusals
    calls.insert_many([make_doc(1000 + i, length=2000, minutes_ago=i % 50,
                                flags=[REFUSAL] if i % 3 == 0 else []) for i in range(30)])
    drift.run_drift()
    drift.run_drift()  # second run must refresh, not duplicate

    active = get("/api/alerts", app_id="bot")["alerts"]
    assert sorted(a["rule"] for a in active) == ["drift_length", "drift_refusal"]

    ack = Client().post(f"/api/alerts/{active[0]['id']}/ack")
    assert ack.status_code == 200 and ack.json()["acknowledged"] is True
    assert len(get("/api/alerts")["alerts"]) == 1
    assert Client().post(f"/api/alerts/{ObjectId()}/ack").status_code == 404
