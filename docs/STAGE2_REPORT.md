# Stage 2 Engineering Report — Intelligence Engine, Performance, Migrations

Date: 2026-11-01. Scope: Stage 2 only (approved). Stage 3 not started.

## Architecture changes
- **New: Central Financial Intelligence Engine** — `backend/app/intelligence/engine.py`.
  A per-request, user-scoped `FinancialIntelligenceEngine` facade over the
  deterministic analytics (`analytics/service.py`), advanced analytics
  (`analytics/advanced.py`) and ML forecasting. Results are memoised per
  instance (request-boundary reuse). It exposes a typed envelope
  (`kind`: fact/forecast/assumption/recommendation, `engine_version`,
  `model_version`, `generated_at`, `data_freshness` = transaction count +
  latest transaction date) and a public endpoint
  `GET /api/v1/intelligence/overview`.
- **Consumers rewired to the engine:** dashboard endpoint
  (`GET /analytics/dashboard`), the agent orchestrator (health,
  subscriptions, affordability, insights intents), the analytics agent and
  the recommendation agent. API contracts and response values are
  unchanged (verified value-for-value on the demo dataset, below).
- **SQL aggregation:** `compute_summary`, `category_breakdown`, `trends`,
  `recurring_expenses`, `dashboard` now use SQL `GROUP BY` queries
  (currency×type totals, category sums, date-grouped daily sums rolled up
  to weeks/months in Python, `LIMIT 10` recents). Advanced analytics use
  grouped queries for budget spend, 3-month affordability sums, 90-day
  income, category×month insight inputs; subscription detection pre-filters
  merchants with ≥3 charges in SQL and loads columns only. Forecasting's
  daily series is built from date-grouped SQL sums. SQL `SUM` over the
  `NUMERIC` columns was verified to return exact `Decimal` values
  (0.10 + 0.20 = Decimal('0.30')) on SQLite; PostgreSQL NUMERIC is exact
  natively. Phase-1 semantics preserved exactly (transfers excluded,
  refunds offset, per-currency separation, weekly keys use calendar
  year + ISO week as before).
- No Redis/Celery or new infrastructure introduced.

## Files created
- `backend/app/intelligence/__init__.py`, `backend/app/intelligence/engine.py`
- `backend/alembic/versions/001_baseline_schema.py` (genuine baseline)
- `backend/alembic/versions/002_txn_composite_indexes.py`
- `scripts/benchmark.py`, `benchmarks/before.json`, `benchmarks/after.json`
- `docs/MIGRATIONS.md`, `docs/STAGE2_REPORT.md`

## Files modified
- `backend/app/analytics/service.py` (rewritten internals, same API/outputs)
- `backend/app/analytics/advanced.py` (SQL-backed internals, same API/outputs)
- `backend/app/ml/forecasting/model.py` (`_daily_series` via grouped SQL)
- `backend/app/agents/orchestrator.py`, `analytics_agent.py`,
  `recommendation_agent.py` (consume the engine)
- `backend/app/api/v1/resources.py` (dashboard via engine, new overview endpoint)
- `backend/app/models/models.py` (3 composite indexes in `__table_args__`)
- `backend/alembic/script.py.mako` (was a stub that silently rendered empty
  migrations — replaced with the standard Alembic template; this was the
  root cause of the old shim-era tooling problem)
- `backend/tests/test_backend.py` (+1 engine envelope/isolation test)

## Migration strategy
See `docs/MIGRATIONS.md`. Baseline `001_baseline` (14 tables, drift-free per
`alembic check`) + additive `002_txn_indexes`. Existing databases use the
documented `stamp 001_baseline` → `upgrade head` path (tested on a copy of
the live dev DB: 3 users / 396 transactions intact). Verified on clean
SQLite **and a real PostgreSQL 16 server** (clean upgrade, drift check,
downgrade/upgrade round-trip, full app smoke with identical results).
Baseline downgrade is documented as destructive/dev-only.

## Performance — before/after (`scripts/benchmark.py`, same methodology,
deterministic seed-7 dataset, SQLite, tracemalloc on dashboard calls)

| Metric (49k txns) | Before | After | Change |
|---|---:|---:|---:|
| Summary | 1,567 ms | 22 ms | ~71× faster |
| Composite dashboard | 19,142 ms | 240 ms | ~80× faster |
| Dashboard memory (tracemalloc peak) | 108.4 MB | 0.6 MB | ~180× less |
| Smart insights | 4,257 ms | 729 ms | ~5.8× faster |
| Forecast (30-day) | 1,544 ms | 147 ms | ~10.5× faster |

| Metric (10k txns) | Before | After |
|---|---:|---:|
| Summary | 322 ms | 6 ms |
| Dashboard | 3,658 ms | 82 ms |
| Insights | 772 ms | 111 ms |
| Forecast | 281 ms | 90 ms |

Query counts were **not** the bottleneck and barely changed (summary 3→3,
dashboard 10→10, insights 12→13, forecast 3→3): the win comes from rows
transferred and Python object materialisation collapsing (49k ORM rows →
a handful of grouped rows). Notes: (1) "before" dashboard timing includes
tracemalloc overhead, as does "after" — the audit's non-instrumented
figure was 6.8 s, so the improvement is >25× under either methodology;
(2) forecast at 1k is ~2.7 s in both runs — first-call statsmodels import
dominates small datasets; (3) insights at 49k (729 ms) still loads the
expense-amount column for an exact median — documented follow-up.

## Correctness evidence (demo dataset, before vs after Stage 2)
Identical values: income ₹543,850 · expense ₹513,339 · net ₹30,511 ·
savings rate 5.61% · USD kept separate ($723) · top category Rent ₹108,000 ·
forecast ₹129,567.95 (exponential smoothing) · health score 70.7 (B) ·
subscriptions 6 / ₹5,166/mo. One cosmetic difference: tied insights may
list in a different order (same set, same numbers).

## Test results
- Backend pytest: **25 passed, 0 failed** (24 pre-existing + 1 new engine test).
- Frontend: tsc pass, production build pass, Vitest 5/5 (in verify run).
- `scripts/verify.sh`: **0 failed stages** (now exercises the genuine migrations).
- PostgreSQL 16: migrations + application smoke **passed** (first time the
  Postgres path has been verified; Docker itself remains untested).

## Known limitations
- Insights' exact-median column load at very large histories (see above).
- `Base.metadata.create_all` still runs at app import for dev convenience;
  production deployments should rely on Alembic (documented).
- Rate limiter remains in-memory/per-process (Stage 10 candidate).
- Benchmarks are SQLite on this VM; PostgreSQL was verified for
  correctness, not benchmarked.

## Remaining tasks
Stage 3 (Health Score v2, Digital Twin, Cash-Flow v2) — awaiting approval.
