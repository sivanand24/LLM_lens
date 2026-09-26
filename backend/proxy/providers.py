"""LLM providers: OpenAIProvider (real) and MockProvider (deterministic failure modes)."""
import json
import random
import time
from dataclasses import dataclass

import httpx


@dataclass
class ProviderResult:
    text: str
    finish_reason: str
    tokens_prompt: int
    tokens_completion: int


class ProviderError(Exception):
    """Provider returned an error or an unusable response."""


class ProviderTimeout(ProviderError):
    """Provider did not answer in time."""


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _messages_text(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: str, timeout_secs: float = 60.0):
        if not api_key:
            raise ValueError("LLM_API_KEY is required for the openai provider (or set USE_MOCK=true)")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_secs,
        )

    def complete(self, model: str, messages: list[dict], expected_format: str | None, tags: dict) -> ProviderResult:
        try:
            resp = self._client.post("/chat/completions", json={"model": model, "messages": messages})
        except httpx.TimeoutException as e:
            raise ProviderTimeout(f"provider timed out: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"provider request failed: {e}") from e

        if resp.status_code >= 400:
            raise ProviderError(f"provider HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            choice = data["choices"][0]
            usage = data.get("usage") or {}
            text = choice["message"].get("content") or ""
            return ProviderResult(
                text=text,
                finish_reason=choice.get("finish_reason") or "stop",
                tokens_prompt=usage.get("prompt_tokens", estimate_tokens(_messages_text(messages))),
                tokens_completion=usage.get("completion_tokens", estimate_tokens(text)),
            )
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"unexpected provider response shape: {e}") from e


# --- Mock provider ---

MOCK_MODES = ("normal", "refuse", "truncate", "bad_json", "slow", "error", "pii", "verbose")

_SENTENCES = [
    "The short answer is that it depends on how your account is configured.",
    "Most users can resolve this from the settings page under the billing tab.",
    "If the issue persists, clearing the cache and signing in again usually helps.",
    "Our records show the change was applied successfully on the last sync.",
    "You can export the report as a CSV file from the dashboard menu.",
    "Refunds are typically processed within five to seven business days.",
    "The API rate limit resets at the start of every minute.",
    "For security reasons, password resets expire after thirty minutes.",
    "Each workspace can have up to fifty active members on the standard plan.",
    "Notifications can be muted per project or globally from your profile.",
    "The integration supports both OAuth and API key authentication.",
    "Scheduled jobs run in UTC, so adjust the time for your local zone.",
    "Archived items are kept for ninety days before permanent deletion.",
    "You will receive a confirmation email once the order has shipped.",
    "Two-factor authentication can be enabled from the security settings.",
]


def _prose(rng: random.Random, min_chars: int, max_chars: int) -> str:
    target = rng.randint(min_chars, max_chars)
    parts: list[str] = []
    while sum(len(p) + 1 for p in parts) < target:
        parts.append(rng.choice(_SENTENCES))
    text = " ".join(parts)
    # Trim whole sentences if we overshot the max.
    while len(text) > max_chars and len(parts) > 1:
        parts.pop()
        text = " ".join(parts)
    return text


class MockProvider:
    name = "mock"

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def complete(self, model: str, messages: list[dict], expected_format: str | None, tags: dict) -> ProviderResult:
        mode = (tags or {}).get("mock_mode", "normal")
        if mode not in MOCK_MODES:
            raise ValueError(f"unknown mock_mode {mode!r}; expected one of {', '.join(MOCK_MODES)}")

        rng = self._rng
        # Simulated network + generation latency so latency charts look realistic.
        time.sleep(rng.uniform(0.3, 2.5) if mode != "slow" else 9.0)

        finish_reason = "stop"
        wants_json = expected_format == "json"

        if mode == "error":
            raise ProviderError(rng.choice([
                "mock provider: upstream 500 Internal Server Error",
                "mock provider: upstream 503 Service Unavailable",
                "mock provider: connection reset by peer",
            ]))
        elif mode == "refuse":
            text = "I'm sorry, but I can't help with that request."
        elif mode == "truncate":
            full = _prose(rng, 400, 900)
            cut = rng.randint(len(full) // 2, len(full) - 10)
            text = full[:cut].rstrip(" .!?") + " and the"
            finish_reason = "length"
        elif mode == "bad_json":
            text = '{"answer": "%s", "confidence": 0.82, "sources": ["kb-114", "kb-207"],}' % rng.choice(_SENTENCES)
        elif mode == "pii":
            text = (
                f"{_prose(rng, 200, 400)} You can reach the account owner at "
                f"jane.doe{rng.randint(10, 99)}@example.com or call +1 415-555-{rng.randint(1000, 9999)}."
            )
        elif mode == "verbose":
            text = _prose(rng, 4200, 6000)
        elif wants_json:  # normal / slow with JSON requested
            text = json.dumps({
                "answer": _prose(rng, 250, 700),
                "confidence": round(rng.uniform(0.6, 0.99), 2),
                "sources": [f"kb-{rng.randint(100, 999)}" for _ in range(rng.randint(1, 3))],
            })
        else:  # normal / slow
            text = _prose(rng, 300, 900)

        return ProviderResult(
            text=text,
            finish_reason=finish_reason,
            tokens_prompt=estimate_tokens(_messages_text(messages)),
            tokens_completion=estimate_tokens(text),
        )


_provider = None


def get_provider():
    """Return the configured provider (singleton)."""
    global _provider
    if _provider is None:
        from django.conf import settings

        if settings.USE_MOCK or settings.LLM_PROVIDER == "mock":
            _provider = MockProvider()
        elif settings.LLM_PROVIDER == "openai":
            _provider = OpenAIProvider(settings.LLM_API_KEY, settings.LLM_BASE_URL)
        else:
            raise ValueError(f"unknown LLM_PROVIDER {settings.LLM_PROVIDER!r}")
    return _provider
