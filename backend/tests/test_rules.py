from checks.registry import run_checks
from checks.rules import (
    check_empty,
    check_error,
    check_format,
    check_latency,
    check_length,
    check_pii,
    check_refusal,
    check_truncation,
)

GOOD_TEXT = "Refunds are typically processed within five to seven business days."
BASELINE = {"resp_len": {"mean": 600, "std": 150, "p95": 850}, "latency_ms": {"p50": 1200, "p95": 2400}}


def make_call(text=GOOD_TEXT, *, status="success", finish_reason="stop", expected_format=None,
              latency_ms=1000, prompt="How long do refunds take?", error=None):
    return {
        "request_id": "req_test",
        "app_id": "test-app",
        "status": status,
        "error": error,
        "prompt": {"messages": [{"role": "user", "content": prompt}]},
        "response": {"text": text, "char_len": len(text), "finish_reason": finish_reason},
        "expected_format": expected_format,
        "latency_ms": latency_ms,
    }


def test_check_error():
    assert check_error(make_call(), {}) is None
    flag = check_error(make_call("", status="provider_error", error="upstream 500"), {})
    assert flag == {"type": "error", "severity": "high", "detail": "upstream 500"}
    assert check_error(make_call("", status="timeout"), {})["type"] == "error"


def test_check_empty():
    assert check_empty(make_call(), {}) is None
    assert check_empty(make_call("   \n "), {})["type"] == "empty"
    # Errored calls have no text by definition; don't double-flag.
    assert check_empty(make_call("", status="provider_error"), {}) is None


def test_check_refusal():
    assert check_refusal(make_call(), {}) is None
    flag = check_refusal(make_call("I'm sorry, but I can't help with that request."), {})
    assert flag["type"] == "refusal" and flag["severity"] == "medium"
    # Curly apostrophe
    assert check_refusal(make_call("I’m unable to share that."), {}) is not None
    # Only the first 300 chars count
    assert check_refusal(make_call("x" * 301 + " I cannot help with that."), {}) is None


def test_check_truncation():
    assert check_truncation(make_call(), {}) is None
    assert check_truncation(make_call(GOOD_TEXT, finish_reason="length"), {})["severity"] == "medium"
    flag = check_truncation(make_call("Refunds are processed within five and the"), {})
    assert flag["type"] == "truncated" and flag["severity"] == "low"
    assert check_truncation(make_call('{"a": 1}'), {}) is None  # JSON ends with }


def test_check_format():
    assert check_format(make_call('{"a": 1}', expected_format="json"), {}) is None
    assert check_format(make_call('```json\n{"a": 1}\n```', expected_format="json"), {}) is None
    flag = check_format(make_call('{"a": 1, "b": [2],}', expected_format="json"), {})
    assert flag["type"] == "format_invalid" and flag["severity"] == "high"
    # Only applies when JSON was expected
    assert check_format(make_call("not json.", expected_format="text"), {}) is None


def test_check_length():
    assert check_length(make_call("x" * 600 + "."), {"baseline": BASELINE}) is None
    assert check_length(make_call("Yes."), {})["type"] == "length_anomaly"
    flag = check_length(make_call("x" * 4500 + "."), {"baseline": BASELINE})
    assert flag["type"] == "length_anomaly" and "z=" in flag["detail"]
    # Refusals are left to check_refusal
    assert check_length(make_call("I'm unable to do that."), {"baseline": BASELINE}) is None
    # No baseline: only the short-response rule applies
    assert check_length(make_call("x" * 4500 + "."), {}) is None


def test_check_latency():
    assert check_latency(make_call(latency_ms=7000), {}) is None
    assert check_latency(make_call(latency_ms=9000), {})["type"] == "slow"
    # With baseline: 2400 * 1.5 = 3600
    assert check_latency(make_call(latency_ms=3500), {"baseline": BASELINE}) is None
    assert check_latency(make_call(latency_ms=3700), {"baseline": BASELINE})["type"] == "slow"
    # Tiny baseline p95 is floored at 1000 ms
    tiny = {"latency_ms": {"p95": 5}}
    assert check_latency(make_call(latency_ms=900), {"baseline": tiny}) is None


def test_check_pii():
    assert check_pii(make_call(), {}) is None
    flag = check_pii(make_call("Contact jane@example.com or +1 415-555-0199."), {})
    assert flag["type"] == "pii" and "email" in flag["detail"] and "phone" in flag["detail"]
    assert "card" in check_pii(make_call("Card on file: 4111 1111 1111 1111."), {})["detail"]
    detail = check_pii(make_call("Aadhaar 1234 5678 9012 is linked."), {})["detail"]
    assert detail == "response contains aadhaar not present in prompt"
    assert "phone" in check_pii(make_call("Call 98765 43210 today."), {})["detail"]
    # Echoing PII the user supplied is not a leak
    assert check_pii(make_call("We will email jane@example.com.", prompt="My email is jane@example.com"), {}) is None


def test_run_checks_aggregates_severity():
    clean = run_checks(make_call(), {})
    assert clean == {"flags": [], "severity": "none", "is_failure": False}

    refused = run_checks(make_call("I'm sorry, but I can't help with that request."), {})
    assert [f["type"] for f in refused["flags"]] == ["refusal"]
    assert refused["severity"] == "medium" and refused["is_failure"] is False

    errored = run_checks(make_call("", status="provider_error", error="boom"), {})
    assert errored["severity"] == "high" and errored["is_failure"] is True
