"""POST /v1/chat — proxy an LLM call, log it, queue it for checks."""
import logging
import secrets
import time
from datetime import datetime, timezone

from rest_framework.decorators import api_view
from rest_framework.response import Response

from checks import worker
from core.auth import require_lens_key
from core.db import get_collection
from proxy.providers import MOCK_MODES, MockProvider, ProviderTimeout, get_provider

log = logging.getLogger(__name__)

EXPECTED_FORMATS = ("json", "text", None)


def _validate(body) -> str | None:
    if not isinstance(body, dict):
        return "body must be a JSON object"
    if not isinstance(body.get("app_id"), str) or not body["app_id"].strip():
        return "app_id is required"
    if not isinstance(body.get("model"), str) or not body["model"].strip():
        return "model is required"
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return "messages must be a non-empty list"
    for m in messages:
        if not isinstance(m, dict) or not isinstance(m.get("role"), str) or not isinstance(m.get("content"), str):
            return "each message needs string 'role' and 'content'"
    if body.get("expected_format") not in EXPECTED_FORMATS:
        return "expected_format must be 'json', 'text' or null"
    if not isinstance(body.get("tags", {}), dict):
        return "tags must be an object"
    return None


@api_view(["POST"])
@require_lens_key
def chat(request):
    body = request.data
    error = _validate(body)
    if error:
        return Response({"error": error}, status=400)

    provider = get_provider()
    tags = body.get("tags") or {}
    if isinstance(provider, MockProvider) and tags.get("mock_mode", "normal") not in MOCK_MODES:
        return Response({"error": f"tags.mock_mode must be one of {', '.join(MOCK_MODES)}"}, status=400)

    messages = body["messages"]
    request_id = f"req_{secrets.token_hex(8)}"
    created_at = datetime.now(timezone.utc)

    result = None
    status, err = "success", None
    started = time.perf_counter()
    try:
        result = provider.complete(body["model"], messages, body.get("expected_format"), tags)
    except ProviderTimeout as e:
        status, err = "timeout", str(e)
    except Exception as e:  # any provider failure is logged, not raised
        status, err = "provider_error", str(e) or e.__class__.__name__
    latency_ms = int((time.perf_counter() - started) * 1000)

    text = result.text if result else ""
    tokens = {
        "prompt": result.tokens_prompt if result else 0,
        "completion": result.tokens_completion if result else 0,
    }
    tokens["total"] = tokens["prompt"] + tokens["completion"]

    doc = {
        "request_id": request_id,
        "app_id": body["app_id"].strip(),
        "model": body["model"],
        "provider": provider.name,
        "prompt": {
            "messages": messages,
            "system": "\n".join(m["content"] for m in messages if m["role"] == "system"),
            "char_len": sum(len(m["content"]) for m in messages),
        },
        "response": {
            "text": text,
            "char_len": len(text),
            "finish_reason": result.finish_reason if result else None,
        },
        "expected_format": body.get("expected_format"),
        "tokens": tokens,
        "latency_ms": latency_ms,
        "status": status,
        "error": err[:1000] if err else None,
        "check_status": "pending",
        "flags": [],
        "severity": "none",
        "is_failure": False,
        "tags": tags,
        "created_at": created_at,
    }

    # Logging must never break the caller's request.
    try:
        inserted = get_collection("llm_calls").insert_one(doc)
        worker.enqueue(inserted.inserted_id)
    except Exception:
        log.exception("failed to log call %s", request_id)

    if status != "success":
        return Response({"request_id": request_id, "status": status, "error": err}, status=502)

    return Response({
        "request_id": request_id,
        "text": text,
        "finish_reason": result.finish_reason,
        "latency_ms": latency_ms,
        "tokens": {"prompt": tokens["prompt"], "completion": tokens["completion"]},
    })
