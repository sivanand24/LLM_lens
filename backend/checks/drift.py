"""Baselines and drift detection. run_drift() is called periodically from the worker thread.

Baselines are frozen snapshots: built automatically once an app has enough history,
refreshed daily or on demand (POST /api/baselines/<app_id>/rebuild). Drift compares
the last hour against the frozen baseline and writes to the alerts collection.
"""
import logging
import math
from datetime import datetime, timedelta, timezone

from core.db import get_collection

log = logging.getLogger(__name__)

BASELINE_WINDOW = timedelta(hours=24)
BASELINE_MAX_AGE = timedelta(hours=24)
BASELINE_MAX_DOCS = 5000
MIN_AUTO_BASELINE_SAMPLE = 50
MIN_MANUAL_BASELINE_SAMPLE = 20

DRIFT_WINDOW = timedelta(hours=1)
DRIFT_MIN_CALLS = 20
LENGTH_DRIFT_SIGMAS = 2.0
REFUSAL_DRIFT_FACTOR = 3.0
REFUSAL_RATE_FLOOR = 0.02  # a zero-refusal baseline would otherwise alert on a single refusal
ALERT_DEDUPE_WINDOW = timedelta(hours=1)


# --- pure helpers (unit-tested) ---

def percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interpolated percentile of an already-sorted list; p in [0, 1]."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(sorted_values[lo])
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def _is_refusal(doc: dict) -> bool:
    return any(f.get("type") == "refusal" for f in doc.get("flags") or [])


def compute_stats(docs: list[dict], healthy_only: bool = False) -> dict:
    """Length / latency / refusal stats over checked, successful calls.

    Response length always excludes refusals so a refusal spike shows up as refusal
    drift, not as a shift in the length distribution. With healthy_only (baselines),
    length and latency come from unflagged calls only, so outliers from an incident
    don't inflate the baseline they will later be judged against.
    """
    shape_docs = [d for d in docs if not d.get("flags")] if healthy_only else docs
    if not shape_docs:
        shape_docs = docs
    lengths = sorted(d["response"]["char_len"] for d in shape_docs if not _is_refusal(d))
    latencies = sorted(d["latency_ms"] for d in shape_docs)
    n = len(lengths)
    mean = sum(lengths) / n if n else 0.0
    std = math.sqrt(sum((x - mean) ** 2 for x in lengths) / (n - 1)) if n > 1 else 0.0
    return {
        "sample_size": len(docs),
        "resp_len": {"mean": round(mean, 1), "std": round(std, 1), "p95": round(percentile(lengths, 0.95), 1)},
        "latency_ms": {"p50": round(percentile(latencies, 0.5), 1), "p95": round(percentile(latencies, 0.95), 1)},
        "refusal_rate": round(sum(_is_refusal(d) for d in docs) / len(docs), 4) if docs else 0.0,
    }


def evaluate_drift(baseline: dict, window: dict) -> list[dict]:
    """Compare last-hour stats with the baseline. Returns [{rule, value, threshold, detail}]."""
    if window["sample_size"] < DRIFT_MIN_CALLS:
        return []
    alerts = []

    base_len = baseline.get("resp_len") or {}
    mean, std = base_len.get("mean"), base_len.get("std")
    cur_mean = window["resp_len"]["mean"]
    if mean is not None and std:
        sigmas = (cur_mean - mean) / std
        if abs(sigmas) > LENGTH_DRIFT_SIGMAS:
            alerts.append({
                "rule": "drift_length",
                "value": round(cur_mean, 1),
                "threshold": round(mean + math.copysign(LENGTH_DRIFT_SIGMAS * std, sigmas), 1),
                "detail": f"last-hour mean length {cur_mean:.0f} chars is {sigmas:+.1f}σ from baseline {mean:.0f}",
            })

    base_rate = baseline.get("refusal_rate") or 0.0
    threshold = max(base_rate, REFUSAL_RATE_FLOOR) * REFUSAL_DRIFT_FACTOR
    cur_rate = window["refusal_rate"]
    if cur_rate > threshold:
        alerts.append({
            "rule": "drift_refusal",
            "value": round(cur_rate, 4),
            "threshold": round(threshold, 4),
            "detail": f"last-hour refusal rate {cur_rate:.1%} vs baseline {base_rate:.1%} (threshold {threshold:.1%})",
        })
    return alerts


# --- Mongo-backed operations ---

def _checked_success(app_id: str, since: datetime, until: datetime) -> list[dict]:
    cursor = get_collection("llm_calls").find(
        {
            "app_id": app_id,
            "status": "success",
            "check_status": "done",
            "created_at": {"$gte": since, "$lt": until},
        },
        {"response.char_len": 1, "latency_ms": 1, "flags.type": 1},
    ).sort("created_at", -1).limit(BASELINE_MAX_DOCS)
    return list(cursor)


def rebuild_baseline(app_id: str, now: datetime | None = None,
                     min_sample: int = MIN_MANUAL_BASELINE_SAMPLE) -> dict | None:
    """Recompute and store the app's baseline. Returns it, or None if there is too little data."""
    now = now or datetime.now(timezone.utc)
    since = now - BASELINE_WINDOW
    docs = _checked_success(app_id, since, now)
    if len(docs) < min_sample:
        return None
    baseline = {"app_id": app_id, "window": {"from": since, "to": now}, **compute_stats(docs, healthy_only=True), "built_at": now}
    get_collection("baselines").replace_one({"app_id": app_id}, baseline, upsert=True)

    from checks import worker  # local import: worker imports this module
    worker.invalidate_baseline(app_id)
    log.info("baseline rebuilt for %s from %d calls", app_id, len(docs))
    return baseline


def _record_alert(app_id: str, alert: dict, now: datetime) -> None:
    alerts = get_collection("alerts")
    # Refresh an open alert for the same rule instead of piling up duplicates every interval.
    existing = alerts.find_one_and_update(
        {"app_id": app_id, "rule": alert["rule"], "acknowledged": False,
         "created_at": {"$gte": now - ALERT_DEDUPE_WINDOW}},
        {"$set": {**alert, "updated_at": now}},
    )
    if existing is None:
        alerts.insert_one({"app_id": app_id, **alert, "created_at": now, "updated_at": now, "acknowledged": False})
        log.warning("drift alert %s for %s: %s", alert["rule"], app_id, alert["detail"])


def run_drift(now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    app_ids = get_collection("llm_calls").distinct("app_id", {"created_at": {"$gte": now - BASELINE_WINDOW}})
    for app_id in app_ids:
        try:
            baseline = get_collection("baselines").find_one({"app_id": app_id})
            if baseline is None or baseline["built_at"] < now - BASELINE_MAX_AGE:
                baseline = rebuild_baseline(app_id, now, MIN_AUTO_BASELINE_SAMPLE) or baseline
            if baseline is None:
                continue
            window = compute_stats(_checked_success(app_id, now - DRIFT_WINDOW, now))
            for alert in evaluate_drift(baseline, window):
                _record_alert(app_id, alert, now)
        except Exception:
            log.exception("drift failed for %s", app_id)
