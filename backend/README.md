# FinSight AI — Backend

FastAPI + SQLAlchemy 2.0 + scikit-learn/statsmodels. PostgreSQL in prod via `DATABASE_URL`; SQLite fallback (`sqlite:///./finsight.db`) when unset, so tests run without Docker.

## Run
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000   # http://localhost:8000/health , docs at /docs
docker compose up --build                            # Postgres + backend alternative
```

## Test / migrate / seed
```bash
.venv/bin/python -m pytest tests/ -q                 # 20 tests (see below)
DATABASE_URL=sqlite:////tmp/alembic_test.db .venv/bin/alembic upgrade head
.venv/bin/python -m app.seed                         # demo@finsight.ai / Demo@1234, ~390 txns over 180 days (dev/demo only)
```

## Key design choices (approved Phase 1 — unchanged)
- Transfers excluded from income/expense; refunds offset expenses. Money is `Numeric`/Decimal in DB and Decimal in analytics (no float summation drift).
- **Multi-currency:** `User.preferred_currency` (INR default) + `Transaction.currency`. Headline analytics sum *only* the primary currency; other currencies are returned separately in `totals_by_currency` and never silently summed.
- Auth: JWT access 30 min (with `jti`), refresh 7 days stored hashed, **rotation** on use, **reuse detection** — presenting a revoked refresh revokes its whole token family (401). Logout revokes refresh tokens *and* denylists the access token's `jti`, so both fail afterwards.
- Backend derives user from JWT on every protected route; client-supplied `user_id` is never trusted. Every resource (transactions, budgets, categories, goals, predictions, anomalies, conversations, reports) is filtered by owner — cross-user access returns 404.
- CSV import is validated row-by-row before insert, deduped by SHA-256 hash (user+date+amount+merchant+description+type): re-importing the same file yields `accepted=0, duplicates=all`. Malformed rows (bad date/amount, missing fields) are counted in `rejected` with per-row `rejected_reasons`; extra columns are ignored; empty file returns a summary, never a crash, and no partial corrupt rows are inserted.
- ML forecasting: chronological split only (no shuffling; split bounds exposed in `/api/v1/ml/evaluation`), compared against naive last-value and moving-average baselines with MAE/RMSE/MAPE per model. With <7 days of history the forecast endpoint returns `insufficient_data: true, predicted_amount: null` — no fabricated forecast and no persisted Prediction. Prediction intervals are returned only for Exponential Smoothing and labelled as such; the moving-average fallback sets `prediction_interval_supported: false`.
- Agents are **read-only**: tools in `app/agents/tools.py` (Pydantic-validated) are analytics/forecast/anomaly/budget/simulator reads only — no create/update/delete transaction tools exist. LLM (`app/integrations/llm.py`) only explains deterministic tool outputs; with no `LLM_API_KEY` a deterministic template fallback is used. Transaction merchant/description text is treated as data: `app/agents/sanitize.py` strips prompt-injection patterns before any such text reaches LLM/anomaly context.
- Anomalies never claim fraud; each has severity, reason, score and ack/dismiss status.

## API (prefix `/api/v1`)
Auth `register|login|refresh|logout|me` · Transactions CRUD + `import|export` · `analytics/dashboard|summary|categories|trends|recurring` · `budgets` (+`alerts|recommendations`) · `categories|accounts|goals|recurring` · `ml/categorize|forecast|forecast/all|evaluation|anomalies` · `predictions` · `anomalies` (+ack/dismiss) · `simulator` (+`compare`) · `assistant/chat|conversations` · `reports/monthly|yearly|export?format=csv|pdf`

Config via `.env` (see `.env.example`): `DATABASE_URL, SECRET_KEY, CORS_ORIGINS, LLM_API_KEY, RATE_LIMIT_PER_MINUTE`.
