"""Dashboard read API. All reads accept ?app_id=&from=&to= (ISO timestamps, default last hour)."""
from datetime import datetime, timedelta, timezone
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from rest_framework.decorators import api_view
from rest_framework.response import Response

from checks import drift
from core.auth import require_lens_key
from core.db import get_collection
from stats import pipelines
from stats.pipelines import Filters

DEFAULT_RANGE = timedelta(hours=1)
MAX_RANGE = timedelta(days=31)
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
SEVERITIES = ("high", "medium", "low", "none")
ACTIVE_ALERT_WINDOW = timedelta(hours=24)


class BadRequest(Exception):
    pass


def _parse_ts(raw: str, name: str) -> datetime:
    try:
        # Python 3.10's fromisoformat does not accept a trailing "Z".
        ts = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        raise BadRequest(f"'{name}' must be an ISO 8601 timestamp")
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def parse_filters(params) -> Filters:
    end = _parse_ts(params["to"], "to") if params.get("to") else datetime.now(timezone.utc)
    start = _parse_ts(params["from"], "from") if params.get("from") else end - DEFAULT_RANGE
    if start >= end:
        raise BadRequest("'from' must be before 'to'")
    if end - start > MAX_RANGE:
        raise BadRequest("range may not exceed 31 days")
    return Filters(start=start, end=end, app_id=params.get("app_id") or None)


def _int_param(params, name: str, default: int, lo: int, hi: int) -> int:
    raw = params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise BadRequest(f"'{name}' must be an integer")
    if not lo <= value <= hi:
        raise BadRequest(f"'{name}' must be between {lo} and {hi}")
    return value


def handles_bad_request(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except BadRequest as e:
            return Response({"error": str(e)}, status=400)

    return wrapper


def _aggregate(pipeline: list[dict]) -> list[dict]:
    return list(get_collection("llm_calls").aggregate(pipeline))


def _window(f: Filters) -> dict:
    return {"from": f.start, "to": f.end, "app_id": f.app_id}


# --- summary ---

EMPTY_SUMMARY = {
    "total_calls": 0, "failures": 0, "flagged": 0, "errors": 0, "pending": 0,
    "avg_latency_ms": None, "p95_latency_ms": None, "total_tokens": 0,
}


def _summary_for(f: Filters) -> dict:
    rows = _aggregate(pipelines.summary_pipeline(f))
    s = {**EMPTY_SUMMARY, **(rows[0] if rows else {})}
    total = s["total_calls"]
    for count_key, rate_key in (("failures", "failure_rate"), ("flagged", "flagged_rate"), ("errors", "error_rate")):
        s[rate_key] = round(s[count_key] / total, 4) if total else 0.0
    for key in ("avg_latency_ms", "p95_latency_ms"):
        if s[key] is not None:
            s[key] = round(s[key], 1)
    return s


def summary_deltas(current: dict, previous: dict) -> dict:
    deltas = {}
    for key, value in current.items():
        prev = previous.get(key)
        deltas[key] = None if value is None or prev is None else round(value - prev, 4)
    return deltas


@api_view(["GET"])
@handles_bad_request
def summary(request):
    f = parse_filters(request.query_params)
    span = f.end - f.start
    current = _summary_for(f)
    previous = _summary_for(Filters(start=f.start - span, end=f.start, app_id=f.app_id))
    return Response({"window": _window(f), **current, "previous": previous,
                     "deltas": summary_deltas(current, previous)})


# --- timeseries ---

def fill_buckets(rows: list[dict], f: Filters) -> list[dict]:
    """Emit one point per bucket across the whole window so charts have no gaps."""
    unit, size, length = pipelines.pick_bucket(f)
    by_bucket = {r["bucket"]: r for r in rows}
    cursor = _truncate(f.start, unit, size)
    out = []
    while cursor < f.end:
        row = by_bucket.get(cursor)
        out.append({
            "bucket": cursor,
            "calls": row["calls"] if row else 0,
            "failures": row["failures"] if row else 0,
            "flagged": row["flagged"] if row else 0,
            "avg_latency_ms": round(row["avg_latency_ms"], 1) if row and row["avg_latency_ms"] is not None else None,
            "p95_latency_ms": round(row["p95_latency_ms"], 1) if row and row["p95_latency_ms"] is not None else None,
        })
        cursor += length
    return out


def _truncate(ts: datetime, unit: str, size: int) -> datetime:
    """Match Mongo's $dateTrunc for the units we use (UTC, epoch-aligned binSize)."""
    ts = ts.astimezone(timezone.utc)
    if unit == "minute":
        return ts.replace(minute=ts.minute - ts.minute % size, second=0, microsecond=0)
    if unit == "hour":
        return ts.replace(hour=ts.hour - ts.hour % size, minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


@api_view(["GET"])
@handles_bad_request
def timeseries(request):
    f = parse_filters(request.query_params)
    unit, size, length = pipelines.pick_bucket(f)
    rows = _aggregate(pipelines.timeseries_pipeline(f))
    return Response({
        "window": _window(f),
        "bucket_secs": int(length.total_seconds()),
        "points": fill_buckets(rows, f),
    })


# --- flags ---

@api_view(["GET"])
@handles_bad_request
def flags(request):
    f = parse_filters(request.query_params)
    return Response({"window": _window(f), "flags": _aggregate(pipelines.flags_pipeline(f))})


# --- calls ---

@api_view(["GET"])
@handles_bad_request
def calls(request):
    params = request.query_params
    f = parse_filters(params)
    severity = params.get("severity") or None
    if severity and severity not in SEVERITIES:
        raise BadRequest(f"'severity' must be one of {', '.join(SEVERITIES)}")
    page = _int_param(params, "page", 1, 1, 10_000)
    page_size = _int_param(params, "page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
    q = (params.get("q") or "").strip()[:200] or None

    [result] = _aggregate(pipelines.calls_pipeline(
        f, flag=params.get("flag") or None, severity=severity, q=q, page=page, page_size=page_size,
    ))
    total = result["total"][0]["n"] if result["total"] else 0
    return Response({
        "window": _window(f),
        "items": result["items"],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@api_view(["GET"])
def call_detail(request, request_id: str):
    doc = get_collection("llm_calls").find_one({"request_id": request_id}, {"_id": 0})
    if doc is None:
        return Response({"error": "not found"}, status=404)
    return Response(doc)


# --- alerts ---

def _alert_out(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@api_view(["GET"])
def alerts(request):
    query = {"acknowledged": False, "created_at": {"$gte": datetime.now(timezone.utc) - ACTIVE_ALERT_WINDOW}}
    if request.query_params.get("app_id"):
        query["app_id"] = request.query_params["app_id"]
    docs = get_collection("alerts").find(query).sort("created_at", -1).limit(50)
    return Response({"alerts": [_alert_out(d) for d in docs]})


@api_view(["POST"])
def acknowledge_alert(request, alert_id: str):
    try:
        oid = ObjectId(alert_id)
    except InvalidId:
        return Response({"error": "invalid alert id"}, status=400)
    doc = get_collection("alerts").find_one_and_update(
        {"_id": oid}, {"$set": {"acknowledged": True, "acknowledged_at": datetime.now(timezone.utc)}},
        return_document=True,
    )
    if doc is None:
        return Response({"error": "not found"}, status=404)
    return Response(_alert_out(doc))


# --- baselines / apps ---

@api_view(["POST"])
@require_lens_key
def rebuild_baseline(request, app_id: str):
    baseline = drift.rebuild_baseline(app_id)
    if baseline is None:
        return Response(
            {"error": f"need at least {drift.MIN_MANUAL_BASELINE_SAMPLE} checked, successful calls "
                      f"in the last 24h to build a baseline for {app_id!r}"},
            status=422,
        )
    baseline.pop("_id", None)
    return Response(baseline)


@api_view(["GET"])
def baseline_detail(request, app_id: str):
    doc = get_collection("baselines").find_one({"app_id": app_id}, {"_id": 0})
    if doc is None:
        return Response({"error": "no baseline yet"}, status=404)
    return Response(doc)


@api_view(["GET"])
@handles_bad_request
def apps(request):
    params = request.query_params.copy()
    params.setdefault("from", (datetime.now(timezone.utc) - timedelta(days=7)).isoformat())
    f = parse_filters(params)
    return Response({"apps": _aggregate(pipelines.apps_pipeline(f))})
