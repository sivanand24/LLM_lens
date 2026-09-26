# CLAUDE.md — LLM Lens

Instructions for Claude Code working in this repo.

---

## Project overview

LLM Lens is a Django + Angular observability proxy for LLM calls.
- `backend/` — Django 5 + DRF; proxy, check pipeline, stats API
- `frontend/` — Angular 17; live dashboard
- `scripts/` — traffic generator and seed prompts

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, Django 5, Django REST Framework |
| Database | MongoDB 7 via `pymongo` (no ORM) |
| Background checks | `threading` + `queue.Queue` (no Celery) |
| Frontend | Angular 17 standalone components, Angular Material, ngx-echarts |
| Dev infra | Docker Compose (Mongo only) |

---

## Repo layout

```
llm-lens/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── manage.py
│   ├── lens/                   # Django settings, root urls
│   ├── core/
│   │   ├── db.py               # pymongo client + ensure_indexes()
│   │   └── auth.py             # X-LLM-Lens-Key header check
│   ├── proxy/
│   │   ├── views.py            # POST /v1/chat
│   │   └── providers.py        # OpenAIProvider, MockProvider
│   ├── checks/
│   │   ├── rules.py            # 8 check functions
│   │   ├── registry.py         # run_checks()
│   │   ├── worker.py           # queue + thread + pending sweep
│   │   ├── drift.py            # window job + alerts
│   │   └── apps.py             # starts worker in ready()
│   ├── stats/
│   │   ├── views.py            # summary, timeseries, flags, calls, alerts
│   │   └── pipelines.py        # Mongo aggregation builders
│   └── tests/
│       └── test_rules.py       # one test per check
├── frontend/
│   └── src/app/
│       ├── core/
│       │   ├── api.service.ts
│       │   └── dashboard.store.ts
│       ├── dashboard/          # KPI cards, trend chart, flag breakdown, alert banner
│       └── logs/               # log table + detail drawer
└── scripts/
    ├── traffic_gen.py
    └── prompts.jsonl
```

---

## Running locally

```bash
# 1. Start Mongo
docker compose up -d mongo

# 2. Backend
cd backend
cp ../.env.example .env          # set USE_MOCK=true for no real API key
pip install -r requirements.txt
python manage.py migrate         # no-op (pymongo); runs ensure_indexes()
python manage.py runserver       # http://localhost:8000

# 3. Frontend
cd frontend
npm install
ng serve                         # http://localhost:4200

# 4. Seed traffic (optional, run before demoing)
cd scripts
python traffic_gen.py --rate 2 --duration 3600 --mix normal=0.95,slow=0.05
```

---

## Environment variables

| Key | Default | Notes |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | Atlas URI in prod |
| `MONGO_DB` | `llm_lens` | |
| `LLM_PROVIDER` | `openai` | `openai` or `mock` |
| `LLM_API_KEY` | — | Not needed when `USE_MOCK=true` |
| `USE_MOCK` | `false` | Set `true` to skip real provider calls |
| `LENS_API_KEY` | `dev-key` | `X-LLM-Lens-Key` header value |
| `DRIFT_INTERVAL_SECS` | `300` | How often the drift job runs |

---

## MongoDB collections

### `llm_calls` (primary)

```json
{
  "_id": "ObjectId",
  "request_id": "req_<hex>",
  "app_id": "string",
  "model": "string",
  "provider": "string",
  "prompt": { "messages": [], "system": "", "char_len": 0 },
  "response": { "text": "", "char_len": 0, "finish_reason": "stop" },
  "expected_format": "json | text | null",
  "tokens": { "prompt": 0, "completion": 0, "total": 0 },
  "latency_ms": 0,
  "status": "success | provider_error | timeout",
  "error": "null | string",
  "check_status": "pending | done",
  "flags": [{ "type": "string", "severity": "high|medium|low", "detail": "string" }],
  "severity": "high | medium | low | none",
  "is_failure": true,
  "tags": {},
  "created_at": "ISODate"
}
```

### `baselines`

```json
{
  "app_id": "string",
  "window": { "from": "ISODate", "to": "ISODate" },
  "sample_size": 0,
  "resp_len": { "mean": 0, "std": 0, "p95": 0 },
  "latency_ms": { "p50": 0, "p95": 0 },
  "refusal_rate": 0.0
}
```

### `alerts`

```json
{
  "app_id": "string",
  "rule": "string",
  "value": 0.0,
  "created_at": "ISODate",
  "acknowledged": false
}
```

**Required indexes — call `core.db.ensure_indexes()` on startup:**

```python
llm_calls.create_index([("created_at", -1)])
llm_calls.create_index([("app_id", 1), ("created_at", -1)])
llm_calls.create_index([("flags.type", 1), ("created_at", -1)])
llm_calls.create_index([("check_status", 1)])
llm_calls.create_index([("request_id", 1)], unique=True)
```

---

## API contract

All dashboard reads accept `?app_id=&from=&to=` (ISO timestamps, default last 1 hour).

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/chat` | Proxy a call; log + return response |
| GET | `/api/stats/summary` | KPI totals + deltas |
| GET | `/api/stats/timeseries` | Per-bucket call/failure/latency series |
| GET | `/api/stats/flags` | Count per flag type |
| GET | `/api/calls` | Paginated log (`?flag=&severity=&q=&page=`) |
| GET | `/api/calls/<request_id>` | Full prompt + response + flags |
| GET | `/api/alerts` | Active drift / threshold alerts |
| POST | `/api/baselines/<app_id>/rebuild` | Recompute baseline |

### `POST /v1/chat` shape

```json
// request
{
  "app_id": "support-bot",
  "model": "gpt-4o-mini",
  "messages": [{ "role": "user", "content": "..." }],
  "expected_format": "json",
  "tags": {}
}

// response 200
{
  "request_id": "req_8f3a2c",
  "text": "...",
  "finish_reason": "stop",
  "latency_ms": 1840,
  "tokens": { "prompt": 98, "completion": 276 }
}
```

Provider errors are logged, then returned as HTTP 502 with `request_id`.

---

## Check pipeline

All checks live in `backend/checks/rules.py`.
Each is a pure function: `check_<name>(call: dict, ctx: dict) -> dict | None`.
Return `None` for no flag, or `{"type": "...", "severity": "high|medium|low", "detail": "..."}`.

| Check fn | Flag type | Logic |
|---|---|---|
| `check_error` | `error` | `status != "success"` |
| `check_empty` | `empty` | stripped response text is empty |
| `check_refusal` | `refusal` | matches ~25 phrases in first 300 chars |
| `check_truncation` | `truncated` | `finish_reason == "length"` or no terminal punctuation |
| `check_format` | `format_invalid` | `expected_format == "json"` and `json.loads` fails |
| `check_length` | `length_anomaly` | `abs(z) > 3` vs app baseline, or response < 20 chars |
| `check_latency` | `slow` | > baseline p95 × 1.5, fallback 8,000 ms |
| `check_pii` | `pii` | regex for email, phone, 16-digit card, 12-digit Aadhaar in response but not prompt |

Register checks in `registry.py`:

```python
CHECKS = [
    check_error, check_empty, check_refusal, check_truncation,
    check_format, check_length, check_latency, check_pii,
]
```

The worker thread (`worker.py`) starts in `checks/apps.py::ChecksConfig.ready()`.
On startup it sweeps all `check_status: "pending"` documents before entering the queue loop.

---

## Drift detection

Runs in `drift.py` every `DRIFT_INTERVAL_SECS` (default 300 s) in the same worker thread.

| Rule | Flag | Condition |
|---|---|---|
| Length drift | `drift_length` | last-hour mean response length moves > 2σ from baseline |
| Refusal-rate drift | `drift_refusal` | last-hour refusal rate > baseline rate × 3 (min 20 calls) |

Results go into `alerts` collection, not onto individual `llm_calls` documents.

---

## Frontend

### Store

`DashboardStore` (`core/dashboard.store.ts`) uses Angular signals + RxJS:

```ts
// polls every 5 seconds while live toggle is on
timer(0, 5000).pipe(
  takeUntilDestroyed(),
  filter(() => this.live()),
  switchMap(() => this.api.getSummary(this.filters()))
).subscribe(data => this.summary.set(data));
```

### Components (all standalone)

| Component | Data |
|---|---|
| `AlertBannerComponent` | `/api/alerts` |
| `KpiCardsComponent` | `/api/stats/summary` |
| `TrendChartComponent` | `/api/stats/timeseries` (ECharts line) |
| `FlagBreakdownComponent` | `/api/stats/flags` (ECharts bar + donut) |
| `LogTableComponent` | `/api/calls` (Material table, paginated) |
| `CallDrawerComponent` | `/api/calls/<id>` (Material sidenav) |

### Severity colour tokens

| Severity | Colour |
|---|---|
| `high` | `--mat-red-600` |
| `medium` | `--mat-amber-600` |
| `low` | `--mat-blue-grey-400` |
| `none` | `--mat-green-600` |

---

## Mock provider modes

Set via `tags.mock_mode` on the request, or randomly by `--mix` weights in the traffic generator.

| Mode | Response | Flag triggered |
|---|---|---|
| `normal` | Plausible 300–900 char answer | none |
| `refuse` | "I'm sorry, but I can't help with that request." | `refusal` |
| `truncate` | Text cut mid-sentence, `finish_reason: length` | `truncated` |
| `bad_json` | JSON with trailing comma | `format_invalid` |
| `slow` | Normal answer after 9 s sleep | `slow` |
| `error` | Raises exception | `error` |
| `pii` | Answer with fake email + phone number | `pii` |
| `verbose` | 4,000+ char answer | `length_anomaly` |

---

## Traffic generator

```bash
# healthy baseline (run before demo to seed 1h of history)
python scripts/traffic_gen.py --rate 2 --duration 3600 --mix normal=0.95,slow=0.05

# incident injection (60 s spike for demo)
python scripts/traffic_gen.py --rate 4 --duration 60 \
  --mix normal=0.4,refuse=0.3,bad_json=0.2,error=0.1
```

---

## Coding conventions

- **No ORM.** All DB access goes through `pymongo` via `core.db.get_collection("llm_calls")`.
- **No Celery / Redis.** The check worker is a `threading.Thread`; keep it that way.
- **One aggregation builder per endpoint** in `stats/pipelines.py`. Views call builders, not raw pipelines.
- **Checks are pure functions.** They take `(call, ctx)` and return a flag dict or `None`. No side effects.
- **Angular components are standalone.** No `NgModule` wrappers.
- **Signals over `BehaviorSubject`** for component-local state in Angular.
- **No `any` in TypeScript.** Type every API response with an interface in `core/models.ts`.

---

## Testing

```bash
# backend unit tests (run from backend/)
python -m pytest tests/ -v

# one test per check rule — add one when you add a check
# tests/test_rules.py  →  test_check_<name>()
```

Frontend: `ng test` (Karma). Cover `DashboardStore` and `ApiService` at minimum.

---

## Cut list (if behind on time)

Drop from the top; the items at the bottom must ship.

1. Semantic (embedding) drift — keep length and refusal drift
2. Donut chart — stacked bar is enough
3. PII check
4. Real LLM provider — demo on `MockProvider` only

**Never cut:** proxy logging, refusal / format / error checks, trend chart, log table + drawer, traffic generator.
