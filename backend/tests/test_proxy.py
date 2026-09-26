"""POST /v1/chat against an in-memory stand-in for the llm_calls collection (no Mongo needed)."""
import pytest
from bson import ObjectId
from django.test import Client, override_settings

from checks import worker
from proxy import providers, views
from proxy.providers import MockProvider

KEY = {"HTTP_X_LLM_LENS_KEY": "dev-key"}


class FakeCollection:
    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        doc["_id"] = ObjectId()
        self.docs.append(doc)
        return type("Result", (), {"inserted_id": doc["_id"]})()


@pytest.fixture
def calls(monkeypatch):
    coll = FakeCollection()
    monkeypatch.setattr(views, "get_collection", lambda name: coll)
    monkeypatch.setattr(views, "get_provider", lambda: MockProvider(seed=1))
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker, "enqueue", lambda _id: None)
    return coll


def post(body, **headers):
    return Client().post("/v1/chat", body, content_type="application/json", **headers)


def body(mode="normal", **extra):
    return {
        "app_id": "support-bot",
        "model": "gpt-4o-mini",
        "messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}],
        "tags": {"mock_mode": mode},
        **extra,
    }


@override_settings(LENS_API_KEY="dev-key")
def test_requires_key(calls):
    assert post(body()).status_code == 401
    assert post(body(), HTTP_X_LLM_LENS_KEY="wrong").status_code == 401
    assert calls.docs == []


@override_settings(LENS_API_KEY="dev-key")
def test_success_logs_pending_call(calls):
    resp = post(body(expected_format="text"), **KEY)
    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"].startswith("req_") and data["finish_reason"] == "stop"
    assert set(data["tokens"]) == {"prompt", "completion"}

    [doc] = calls.docs
    assert doc["request_id"] == data["request_id"]
    assert doc["check_status"] == "pending" and doc["status"] == "success"
    assert doc["prompt"]["system"] == "Be brief."
    assert doc["response"]["char_len"] == len(data["text"])
    assert doc["tokens"]["total"] == doc["tokens"]["prompt"] + doc["tokens"]["completion"]


@override_settings(LENS_API_KEY="dev-key")
def test_provider_error_logged_and_502(calls):
    resp = post(body("error"), **KEY)
    assert resp.status_code == 502
    assert resp.json()["request_id"] == calls.docs[0]["request_id"]
    assert calls.docs[0]["status"] == "provider_error" and calls.docs[0]["error"]


@override_settings(LENS_API_KEY="dev-key")
@pytest.mark.parametrize("bad", [
    {"model": "m", "messages": [{"role": "user", "content": "x"}]},
    {"app_id": "a", "model": "m", "messages": []},
    {"app_id": "a", "model": "m", "messages": [{"role": "user", "content": "x"}], "expected_format": "xml"},
    {"app_id": "a", "model": "m", "messages": [{"role": "user", "content": "x"}], "tags": {"mock_mode": "nope"}},
])
def test_validation(calls, bad):
    assert post(bad, **KEY).status_code == 400
    assert calls.docs == []
