from checks.drift import compute_stats, evaluate_drift, percentile

BASELINE = {"resp_len": {"mean": 600, "std": 150}, "refusal_rate": 0.02}


def call(length=600, latency=1000, refusal=False):
    return {
        "response": {"char_len": length},
        "latency_ms": latency,
        "flags": [{"type": "refusal"}] if refusal else [],
    }


def window(mean=600, refusal_rate=0.0, n=40):
    return {"sample_size": n, "resp_len": {"mean": mean}, "refusal_rate": refusal_rate}


def test_percentile():
    assert percentile([], 0.95) == 0.0
    assert percentile([10], 0.5) == 10
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([0, 10], 0.95) == 9.5


def test_compute_stats_excludes_refusals_from_length():
    docs = [call(500), call(700), call(40, refusal=True), call(600, latency=3000)]
    s = compute_stats(docs)
    assert s["sample_size"] == 4
    assert s["resp_len"]["mean"] == 600
    assert s["refusal_rate"] == 0.25
    assert s["latency_ms"]["p50"] == 1000


def test_compute_stats_healthy_only_ignores_flagged_outliers():
    verbose = {**call(5000), "flags": [{"type": "length_anomaly"}]}
    slow = {**call(600, latency=9000), "flags": [{"type": "slow"}]}
    docs = [call(500), call(700), verbose, slow, call(40, refusal=True)]
    s = compute_stats(docs, healthy_only=True)
    assert s["resp_len"]["mean"] == 600 and s["latency_ms"]["p95"] == 1000
    assert s["refusal_rate"] == 0.2  # refusal rate still counts every call
    assert compute_stats(docs)["resp_len"]["mean"] > 1000


def test_no_drift_below_min_calls():
    assert evaluate_drift(BASELINE, window(mean=5000, refusal_rate=0.9, n=19)) == []


def test_length_drift():
    assert evaluate_drift(BASELINE, window(mean=850)) == []  # +1.7σ
    [alert] = evaluate_drift(BASELINE, window(mean=950))  # +2.3σ
    assert alert["rule"] == "drift_length" and alert["threshold"] == 900
    [alert] = evaluate_drift(BASELINE, window(mean=250))  # -2.3σ
    assert alert["threshold"] == 300


def test_refusal_drift():
    assert evaluate_drift(BASELINE, window(refusal_rate=0.05)) == []  # threshold 0.06
    [alert] = evaluate_drift(BASELINE, window(refusal_rate=0.3))
    assert alert["rule"] == "drift_refusal" and alert["value"] == 0.3
    # Zero-refusal baseline uses the 2% floor -> threshold 6%
    zero = {**BASELINE, "refusal_rate": 0.0}
    assert evaluate_drift(zero, window(refusal_rate=0.05)) == []
    assert evaluate_drift(zero, window(refusal_rate=0.1))[0]["threshold"] == 0.06
