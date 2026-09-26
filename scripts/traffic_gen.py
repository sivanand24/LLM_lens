#!/usr/bin/env python
"""Send synthetic traffic through the LLM Lens proxy.

Examples:
    # healthy baseline
    python traffic_gen.py --rate 2 --duration 3600 --mix normal=0.95,slow=0.05
    # incident injection
    python traffic_gen.py --rate 4 --duration 60 --mix normal=0.4,refuse=0.3,bad_json=0.2,error=0.1

Stdlib only, so it runs without installing anything.
"""
import argparse
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODES = ("normal", "refuse", "truncate", "bad_json", "slow", "error", "pii", "verbose")
MODELS = ("gpt-4o-mini", "gpt-4o-mini", "gpt-4o")


def parse_mix(raw: str) -> tuple[list[str], list[float]]:
    modes, weights = [], []
    for part in raw.split(","):
        name, _, weight = part.partition("=")
        name = name.strip()
        if name not in MODES:
            raise argparse.ArgumentTypeError(f"unknown mode {name!r}; choose from {', '.join(MODES)}")
        try:
            w = float(weight)
        except ValueError:
            raise argparse.ArgumentTypeError(f"bad weight in {part!r}")
        if w < 0:
            raise argparse.ArgumentTypeError(f"negative weight in {part!r}")
        modes.append(name)
        weights.append(w)
    if not sum(weights):
        raise argparse.ArgumentTypeError("mix weights must not all be zero")
    return modes, weights


def load_prompts(path: Path, apps: set[str] | None) -> list[dict]:
    prompts = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if apps:
        prompts = [p for p in prompts if p["app_id"] in apps]
    if not prompts:
        sys.exit(f"no prompts found in {path}" + (f" for apps {sorted(apps)}" if apps else ""))
    return prompts


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.outcomes: Counter[str] = Counter()
        self.modes: Counter[str] = Counter()
        self.latencies: list[int] = []

    def record(self, mode: str, outcome: str, latency_ms: int | None):
        with self.lock:
            self.modes[mode] += 1
            self.outcomes[outcome] += 1
            if latency_ms is not None:
                self.latencies.append(latency_ms)

    def line(self) -> str:
        with self.lock:
            n = sum(self.outcomes.values())
            avg = sum(self.latencies) / len(self.latencies) if self.latencies else 0
            outcomes = " ".join(f"{k}={v}" for k, v in sorted(self.outcomes.items()))
            return f"sent={n} {outcomes} avg_latency={avg:.0f}ms"


def send(args, prompt: dict, mode: str, stats: Stats) -> None:
    # bad_json only means something when JSON was requested.
    expected_format = "json" if mode == "bad_json" else prompt.get("expected_format")
    body = {
        "app_id": prompt["app_id"],
        "model": random.choice(MODELS),
        "messages": prompt["messages"],
        "expected_format": expected_format,
        "tags": {"mock_mode": mode, "source": "traffic_gen"},
    }
    req = urllib.request.Request(
        f"{args.url.rstrip('/')}/v1/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-LLM-Lens-Key": args.key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            data = json.loads(resp.read())
            stats.record(mode, "ok", data.get("latency_ms"))
    except urllib.error.HTTPError as e:
        stats.record(mode, f"http_{e.code}", None)
        if e.code in (400, 401):
            print(f"  {e.code}: {e.read().decode(errors='replace')[:200]}", file=sys.stderr)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        stats.record(mode, "conn_error", None)
        if args.verbose:
            print(f"  connection error: {e}", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--key", default="dev-key", help="X-LLM-Lens-Key value")
    p.add_argument("--rate", type=float, default=2.0, help="requests per second")
    p.add_argument("--duration", type=float, default=60, help="seconds to run")
    p.add_argument("--mix", type=parse_mix, default=parse_mix("normal=1"),
                   help="mode weights, e.g. normal=0.9,refuse=0.1")
    p.add_argument("--apps", help="comma-separated app_ids to restrict prompts to")
    p.add_argument("--prompts", type=Path, default=Path(__file__).with_name("prompts.jsonl"))
    p.add_argument("--workers", type=int, default=32, help="max concurrent requests")
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--seed", type=int)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    if args.rate <= 0:
        p.error("--rate must be positive")
    if args.seed is not None:
        random.seed(args.seed)

    prompts = load_prompts(args.prompts, set(args.apps.split(",")) if args.apps else None)
    modes, weights = args.mix
    stats = Stats()
    print(f"-> {args.url} at {args.rate}/s for {args.duration:.0f}s, mix: "
          + ", ".join(f"{m}={w:g}" for m, w in zip(modes, weights)))

    start = time.monotonic()
    next_report = start + 10
    sent = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        try:
            while (now := time.monotonic()) - start < args.duration:
                # Fixed-rate schedule; don't drift if a tick runs late.
                due = start + sent / args.rate
                if now < due:
                    time.sleep(min(due - now, 0.5))
                    continue
                mode = random.choices(modes, weights)[0]
                pool.submit(send, args, random.choice(prompts), mode, stats)
                sent += 1
                if now >= next_report:
                    print(f"[{now - start:5.0f}s] {stats.line()}")
                    next_report += 10
        except KeyboardInterrupt:
            print("\ninterrupted; waiting for in-flight requests...")
            pool.shutdown(wait=True, cancel_futures=True)

    print(f"done: {stats.line()}")
    print("modes: " + " ".join(f"{k}={v}" for k, v in sorted(stats.modes.items())))


if __name__ == "__main__":
    main()
