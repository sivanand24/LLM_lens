"""Background check worker: one daemon thread, an in-memory queue, and a pending sweep.

The queue is only a speed-up. Durability comes from check_status="pending" in Mongo:
anything missed (full queue, crash, restart) is picked up by the startup sweep.
"""
import logging
import queue
import threading
import time

from bson import ObjectId
from django.conf import settings

from checks import drift
from checks.registry import run_checks
from core.db import get_collection

log = logging.getLogger(__name__)

QUEUE_WAIT_SECS = 5
BASELINE_CACHE_SECS = 60

_queue: "queue.Queue[ObjectId]" = queue.Queue(maxsize=10_000)
_thread: threading.Thread | None = None
_start_lock = threading.Lock()
_baseline_cache: dict[str, tuple[float, dict | None]] = {}


def enqueue(call_id: ObjectId) -> None:
    try:
        _queue.put_nowait(call_id)
    except queue.Full:
        log.warning("check queue full; %s will be picked up by the next sweep", call_id)


def start() -> None:
    global _thread
    with _start_lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_run, name="llm-lens-checks", daemon=True)
        _thread.start()
        log.info("check worker started")


def _get_baseline(app_id: str) -> dict | None:
    now = time.monotonic()
    cached = _baseline_cache.get(app_id)
    if cached and now - cached[0] < BASELINE_CACHE_SECS:
        return cached[1]
    baseline = get_collection("baselines").find_one({"app_id": app_id})
    _baseline_cache[app_id] = (now, baseline)
    return baseline


def invalidate_baseline(app_id: str) -> None:
    _baseline_cache.pop(app_id, None)


def process_doc(doc: dict) -> None:
    ctx = {"baseline": _get_baseline(doc["app_id"])}
    result = run_checks(doc, ctx)
    # Filter on pending so a doc handled by both the sweep and the queue is only written once.
    get_collection("llm_calls").update_one(
        {"_id": doc["_id"], "check_status": "pending"},
        {"$set": {**result, "check_status": "done"}},
    )


def process(call_id: ObjectId) -> None:
    doc = get_collection("llm_calls").find_one({"_id": call_id, "check_status": "pending"})
    if doc:
        process_doc(doc)


def sweep_pending() -> int:
    count = 0
    cursor = get_collection("llm_calls").find({"check_status": "pending"}).sort("created_at", 1)
    for doc in cursor:
        try:
            process_doc(doc)
            count += 1
        except Exception:
            log.exception("sweep failed on %s", doc.get("request_id"))
    return count


def _run() -> None:
    # Sweep first; retry with backoff if Mongo is not up yet.
    backoff = 1
    while True:
        try:
            n = sweep_pending()
            log.info("startup sweep processed %d pending calls", n)
            break
        except Exception:
            log.exception("startup sweep failed; retrying in %ds", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

    next_drift = time.monotonic()  # first drift run right after the sweep
    while True:
        try:
            call_id = _queue.get(timeout=QUEUE_WAIT_SECS)
        except queue.Empty:
            call_id = None
        if call_id is not None:
            try:
                process(call_id)
            except Exception:
                log.exception("check processing failed for %s", call_id)
            finally:
                _queue.task_done()

        if time.monotonic() >= next_drift:
            try:
                drift.run_drift()
            except Exception:
                log.exception("drift job failed")
            next_drift = time.monotonic() + settings.DRIFT_INTERVAL_SECS
