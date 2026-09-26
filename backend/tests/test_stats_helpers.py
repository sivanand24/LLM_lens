from datetime import datetime, timedelta, timezone

import pytest

from stats.pipelines import Filters, pick_bucket
from stats.views import BadRequest, fill_buckets, parse_filters, summary_deltas

T0 = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)


def test_parse_filters_defaults_to_last_hour():
    f = parse_filters({})
    assert f.end - f.start == timedelta(hours=1)
    assert f.app_id is None


def test_parse_filters_accepts_z_and_naive():
    f = parse_filters({"from": "2026-09-26T10:00:00Z", "to": "2026-09-26T11:00:00", "app_id": "bot"})
    assert f.start == T0 and f.end == T0 + timedelta(hours=1) and f.app_id == "bot"


@pytest.mark.parametrize("params", [
    {"from": "yesterday"},
    {"from": "2026-09-26T11:00:00Z", "to": "2026-09-26T10:00:00Z"},
    {"from": "2026-01-01T00:00:00Z", "to": "2026-09-26T10:00:00Z"},
])
def test_parse_filters_rejects(params):
    with pytest.raises(BadRequest):
        parse_filters(params)


@pytest.mark.parametrize("span,expected", [
    (timedelta(hours=1), timedelta(minutes=1)),
    (timedelta(hours=6), timedelta(minutes=5)),
    (timedelta(days=1), timedelta(hours=1)),
    (timedelta(days=7), timedelta(days=1)),
])
def test_pick_bucket(span, expected):
    assert pick_bucket(Filters(start=T0 - span, end=T0))[2] == expected


def test_fill_buckets_fills_gaps():
    f = Filters(start=T0 + timedelta(seconds=30), end=T0 + timedelta(minutes=3))
    rows = [{"bucket": T0 + timedelta(minutes=1), "calls": 4, "failures": 1, "flagged": 2,
             "avg_latency_ms": 1234.56, "p95_latency_ms": 2000.0}]
    points = fill_buckets(rows, f)
    assert [p["bucket"] for p in points] == [T0 + timedelta(minutes=i) for i in range(3)]
    assert [p["calls"] for p in points] == [0, 4, 0]
    assert points[1]["avg_latency_ms"] == 1234.6
    assert points[0]["avg_latency_ms"] is None


def test_fill_buckets_five_minute_alignment():
    f = Filters(start=T0 + timedelta(minutes=7), end=T0 + timedelta(hours=6))
    points = fill_buckets([], f)
    assert points[0]["bucket"] == T0 + timedelta(minutes=5)
    assert all(p["bucket"].minute % 5 == 0 for p in points)


def test_summary_deltas():
    assert summary_deltas({"total_calls": 10, "p95_latency_ms": None, "failure_rate": 0.2},
                          {"total_calls": 4, "p95_latency_ms": 900.0, "failure_rate": 0.05}) == {
        "total_calls": 6, "p95_latency_ms": None, "failure_rate": 0.15,
    }
