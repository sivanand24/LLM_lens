"""Mongo aggregation builders — one per stats endpoint. Views call these, never raw pipelines."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

# (max range, $dateTrunc unit, binSize, bucket length)
BUCKET_RULES = [
    (timedelta(hours=2), "minute", 1, timedelta(minutes=1)),
    (timedelta(hours=12), "minute", 5, timedelta(minutes=5)),
    (timedelta(days=3), "hour", 1, timedelta(hours=1)),
    (timedelta.max, "day", 1, timedelta(days=1)),
]

LIST_PREVIEW_CHARS = 140


@dataclass(frozen=True)
class Filters:
    start: datetime
    end: datetime
    app_id: str | None = None


def base_match(f: Filters) -> dict:
    match: dict = {"created_at": {"$gte": f.start, "$lt": f.end}}
    if f.app_id:
        match["app_id"] = f.app_id
    return match


def pick_bucket(f: Filters) -> tuple[str, int, timedelta]:
    span = f.end - f.start
    for max_span, unit, size, length in BUCKET_RULES:
        if span <= max_span:
            return unit, size, length
    raise AssertionError("unreachable")


def _p95(field: str) -> dict:
    return {"$percentile": {"input": field, "p": [0.95], "method": "approximate"}}


def _count_if(cond) -> dict:
    return {"$sum": {"$cond": [cond, 1, 0]}}


_FLAGGED = {"$gt": [{"$size": {"$ifNull": ["$flags", []]}}, 0]}
_ERRORED = {"$ne": ["$status", "success"]}


def summary_pipeline(f: Filters) -> list[dict]:
    return [
        {"$match": base_match(f)},
        {"$group": {
            "_id": None,
            "total_calls": {"$sum": 1},
            "failures": _count_if("$is_failure"),
            "flagged": _count_if(_FLAGGED),
            "errors": _count_if(_ERRORED),
            "pending": _count_if({"$eq": ["$check_status", "pending"]}),
            "avg_latency_ms": {"$avg": "$latency_ms"},
            "p95_latency_ms": _p95("$latency_ms"),
            "total_tokens": {"$sum": "$tokens.total"},
        }},
        # $percentile yields an array: unwrap the single p95 value.
        {"$set": {"p95_latency_ms": {"$arrayElemAt": ["$p95_latency_ms", 0]}}},
        {"$unset": "_id"},
    ]


def timeseries_pipeline(f: Filters) -> list[dict]:
    unit, size, _ = pick_bucket(f)
    return [
        {"$match": base_match(f)},
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$created_at", "unit": unit, "binSize": size}},
            "calls": {"$sum": 1},
            "failures": _count_if("$is_failure"),
            "flagged": _count_if(_FLAGGED),
            "avg_latency_ms": {"$avg": "$latency_ms"},
            "p95_latency_ms": _p95("$latency_ms"),
        }},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "bucket": "$_id", "calls": 1, "failures": 1, "flagged": 1,
                      "avg_latency_ms": 1, "p95_latency_ms": {"$arrayElemAt": ["$p95_latency_ms", 0]}}},
    ]


def flags_pipeline(f: Filters) -> list[dict]:
    return [
        {"$match": {**base_match(f), "flags.0": {"$exists": True}}},
        {"$unwind": "$flags"},
        {"$group": {"_id": {"type": "$flags.type", "severity": "$flags.severity"}, "count": {"$sum": 1}}},
        {"$group": {
            "_id": "$_id.type",
            "count": {"$sum": "$count"},
            "by_severity": {"$push": {"k": "$_id.severity", "v": "$count"}},
        }},
        {"$project": {"_id": 0, "type": "$_id", "count": 1, "by_severity": {"$arrayToObject": "$by_severity"}}},
        {"$sort": {"count": -1, "type": 1}},
    ]


def calls_pipeline(f: Filters, *, flag: str | None, severity: str | None, q: str | None,
                   page: int, page_size: int) -> list[dict]:
    match = base_match(f)
    if flag:
        match["flags.type"] = flag
    if severity:
        match["severity"] = severity
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        match["$or"] = [{"request_id": rx}, {"response.text": rx}, {"prompt.messages.content": rx}]

    return [
        {"$match": match},
        {"$sort": {"created_at": -1}},
        {"$facet": {
            "items": [
                {"$skip": (page - 1) * page_size},
                {"$limit": page_size},
                {"$project": {
                    "_id": 0,
                    "request_id": 1, "app_id": 1, "model": 1, "status": 1, "latency_ms": 1,
                    "severity": 1, "is_failure": 1, "check_status": 1, "created_at": 1,
                    "tokens": "$tokens.total",
                    "flags": "$flags.type",
                    "prompt_preview": {"$substrCP": [
                        {"$ifNull": [{"$arrayElemAt": ["$prompt.messages.content", -1]}, ""]},
                        0, LIST_PREVIEW_CHARS]},
                    "response_preview": {"$substrCP": [{"$ifNull": ["$response.text", ""]}, 0, LIST_PREVIEW_CHARS]},
                }},
            ],
            "total": [{"$count": "n"}],
        }},
    ]


def apps_pipeline(f: Filters) -> list[dict]:
    return [
        {"$match": {"created_at": {"$gte": f.start, "$lt": f.end}}},
        {"$group": {"_id": "$app_id", "calls": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "app_id": "$_id", "calls": 1}},
    ]
