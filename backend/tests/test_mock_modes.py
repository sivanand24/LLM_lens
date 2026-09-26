"""Each MockProvider mode should trigger exactly the flag CLAUDE.md promises."""
import pytest

from checks.registry import run_checks
from proxy import providers
from proxy.providers import MockProvider, ProviderError

BASELINE = {"resp_len": {"mean": 600, "std": 170, "p95": 870}, "latency_ms": {"p50": 1400, "p95": 2400}}
MESSAGES = [{"role": "user", "content": "How do I export my report?"}]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)


def run_mode(mode, expected_format=None, latency_ms=1200, seed=0):
    provider = MockProvider(seed=seed)
    try:
        r = provider.complete("gpt-4o-mini", MESSAGES, expected_format, {"mock_mode": mode})
        call = {"status": "success", "response": {"text": r.text, "finish_reason": r.finish_reason}}
    except ProviderError as e:
        call = {"status": "provider_error", "error": str(e), "response": {"text": "", "finish_reason": None}}
    call.update(prompt={"messages": MESSAGES}, expected_format=expected_format, latency_ms=latency_ms)
    return {f["type"] for f in run_checks(call, {"baseline": BASELINE})["flags"]}


@pytest.mark.parametrize("seed", range(20))
def test_normal_is_clean(seed):
    assert run_mode("normal", seed=seed) == set()
    assert run_mode("normal", expected_format="json", seed=seed) == set()


@pytest.mark.parametrize("mode,expected_format,latency_ms,flag", [
    ("refuse", None, 1200, "refusal"),
    ("truncate", None, 1200, "truncated"),
    ("bad_json", "json", 1200, "format_invalid"),
    ("slow", None, 9000, "slow"),
    ("error", None, 5, "error"),
    ("pii", None, 1200, "pii"),
    ("verbose", None, 1200, "length_anomaly"),
])
def test_failure_modes(mode, expected_format, latency_ms, flag):
    assert run_mode(mode, expected_format, latency_ms) == {flag}


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        MockProvider().complete("m", MESSAGES, None, {"mock_mode": "nope"})
