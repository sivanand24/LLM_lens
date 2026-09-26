"""Check functions. Each is pure: check_<name>(call, ctx) -> flag dict | None.

`call` is an llm_calls document. `ctx` may contain:
    baseline: the app's baselines document, or None
"""
import json
import re

LATENCY_FALLBACK_MS = 8000
LATENCY_MIN_THRESHOLD_MS = 1000  # guards against tiny baselines flagging everything
LENGTH_Z_THRESHOLD = 3.0
LENGTH_MIN_CHARS = 20
REFUSAL_WINDOW = 300

REFUSAL_PHRASES = [
    "i'm sorry, but i can't",
    "i'm sorry, but i cannot",
    "i am sorry, but i cannot",
    "sorry, i can't help",
    "sorry, i cannot help",
    "i can't help with that",
    "i cannot help with that",
    "i can't assist with",
    "i cannot assist with",
    "i'm unable to",
    "i am unable to",
    "i'm not able to",
    "i am not able to",
    "i won't be able to",
    "i can't provide",
    "i cannot provide",
    "i can't comply",
    "i cannot comply",
    "i must decline",
    "i have to decline",
    "i'm not comfortable",
    "as an ai language model",
    "as an ai, i",
    "against my guidelines",
    "i'm not allowed to",
    "i am not allowed to",
    "that request violates",
]

TERMINAL_CHARS = set('.!?"\')]}`*”’…')

_PII_PATTERNS = {
    # Card before aadhaar/phone: a 16-digit card also contains 12-digit runs.
    "card": re.compile(r"(?<!\d)(?<!\d[ -])(?:\d{4}[ -]?){3}\d{4}(?![ -]?\d)"),
    "aadhaar": re.compile(r"(?<!\d)(?<!\d[ -])\d{4}[ -]?\d{4}[ -]?\d{4}(?![ -]?\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(
        r"(?<![\d+])(?<!\d[ -])(?:"
        r"(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}"  # NANP-style
        r"|(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}"  # Indian mobile
        r")(?![ -]?\d)"
    ),
}


def _flag(type_: str, severity: str, detail: str) -> dict:
    return {"type": type_, "severity": severity, "detail": detail}


def _text(call: dict) -> str:
    return (call.get("response") or {}).get("text") or ""


def _ok(call: dict) -> bool:
    return call.get("status") == "success"


def check_error(call: dict, ctx: dict) -> dict | None:
    if call.get("status") != "success":
        return _flag("error", "high", call.get("error") or f"status={call.get('status')}")
    return None


def check_empty(call: dict, ctx: dict) -> dict | None:
    if _ok(call) and not _text(call).strip():
        return _flag("empty", "high", "response text is empty")
    return None


def _refusal_phrase(text: str) -> str | None:
    head = text[:REFUSAL_WINDOW].lower().replace("’", "'")
    return next((p for p in REFUSAL_PHRASES if p in head), None)


def check_refusal(call: dict, ctx: dict) -> dict | None:
    phrase = _refusal_phrase(_text(call))
    if phrase:
        return _flag("refusal", "medium", f'matched "{phrase}"')
    return None


def check_truncation(call: dict, ctx: dict) -> dict | None:
    text = _text(call).strip()
    if not _ok(call) or not text:
        return None
    if (call.get("response") or {}).get("finish_reason") == "length":
        return _flag("truncated", "medium", "finish_reason=length")
    if text[-1] not in TERMINAL_CHARS:
        return _flag("truncated", "low", f"no terminal punctuation (ends with {text[-15:]!r})")
    return None


def _strip_code_fence(text: str) -> str:
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else text


def check_format(call: dict, ctx: dict) -> dict | None:
    text = _text(call).strip()
    if call.get("expected_format") != "json" or not _ok(call) or not text:
        return None
    try:
        json.loads(_strip_code_fence(text))
    except ValueError as e:
        return _flag("format_invalid", "high", f"invalid JSON: {e}")
    return None


def check_length(call: dict, ctx: dict) -> dict | None:
    text = _text(call).strip()
    if not _ok(call) or not text:
        return None  # empty is check_empty's job
    if _refusal_phrase(text):
        return None  # refusals are short by nature; check_refusal already flags them
    n = len(text)
    if n < LENGTH_MIN_CHARS:
        return _flag("length_anomaly", "low", f"response only {n} chars")
    baseline = ctx.get("baseline") or {}
    stats = baseline.get("resp_len") or {}
    mean, std = stats.get("mean"), stats.get("std")
    if mean is not None and std:
        z = (n - mean) / std
        if abs(z) > LENGTH_Z_THRESHOLD:
            return _flag("length_anomaly", "low", f"length {n} chars, z={z:.1f} vs baseline mean {mean:.0f}")
    return None


def check_latency(call: dict, ctx: dict) -> dict | None:
    latency = call.get("latency_ms")
    if latency is None:
        return None
    baseline = ctx.get("baseline") or {}
    p95 = (baseline.get("latency_ms") or {}).get("p95")
    if p95:
        threshold = max(p95 * 1.5, LATENCY_MIN_THRESHOLD_MS)
        source = f"baseline p95 {p95:.0f} ms x 1.5"
    else:
        threshold = LATENCY_FALLBACK_MS
        source = "fallback"
    if latency > threshold:
        return _flag("slow", "low", f"{latency} ms > {threshold:.0f} ms ({source})")
    return None


def _normalize(value: str) -> str:
    return re.sub(r"[\s().+-]", "", value).lower()


def check_pii(call: dict, ctx: dict) -> dict | None:
    text = _text(call)
    if not text:
        return None
    prompt_msgs = (call.get("prompt") or {}).get("messages") or []
    prompt_norm = _normalize(" ".join(str(m.get("content", "")) for m in prompt_msgs))

    found: list[str] = []
    consumed: list[tuple[int, int]] = []
    for kind, pattern in _PII_PATTERNS.items():
        for m in pattern.finditer(text):
            if any(s <= m.start() < e for s, e in consumed):
                continue  # already matched as a more specific kind
            consumed.append(m.span())
            if _normalize(m.group()) not in prompt_norm and kind not in found:
                found.append(kind)
    if found:
        return _flag("pii", "high", f"response contains {', '.join(found)} not present in prompt")
    return None
