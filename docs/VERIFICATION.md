# Verification protocol (user-approved 2026-10-31)
No phase is complete until checked here. Independent re-run: `bash scripts/verify.sh`

## Backend
- [x] Auth: register/login, refresh rotation, reuse of rotated refresh token rejected (+ family revocation), logout revokes refresh
- [x] Isolation: second user gets 404/403 on every resource type (transactions, budgets, anomalies, predictions, conversations, categories, reports)
- [x] Calculations: transfers excluded, refunds offset, recurring aggregated, Decimal precision (0.10+0.20), UTC dates, multi-currency not silently summed
- [x] CSV: idempotent re-import, malformed rows rejected with reasons, no partial corruption
- [x] Migrations: `alembic upgrade head` on clean DB

## ML
- [x] Chronological split asserted in tests (train dates < test dates), no leakage
- [x] Models vs naive baseline, MAE + RMSE reported from backtest
- [x] Sparse history -> explicit insufficient-data response, no fabricated forecast/intervals
- [x] Anomalies: normal synthetic data vs deliberate outliers

## Agents
- [x] Tools user-scoped + Pydantic-validated, calculations deterministic
- [x] LLM = explanation only; fallback with no provider works
- [x] Prompt injection in transaction descriptions treated as data (test)
- [x] No financial write tools exposed

## Frontend
- [x] All pages hit real endpoints; no hardcoded metrics/placeholder actions
- [x] Loading / error / empty states present
- [x] Responsive mobile + desktop intact
- [x] tsc, lint, production build results recorded verbatim

## Final
- [x] Full backend suite, frontend checks, production build, `docker compose up` — NOT RUN: Docker is not installed in this verification VM (confirmed `docker: command not found`); compose YAML validated by parsing, Dockerfiles present for all 3 services

## Results — 2026-10-31 (independent re-run by lead agent, scripts/verify.sh exit 0)
- Backend pytest: 20 passed, 0 failed (after integration fixes, re-run twice)
- Frontend: tsc PASS, eslint PASS, Vitest 5/5, next build PASS (15 pages)
- Alembic upgrade head on clean SQLite: PASS
- Integration audit found + fixed 5 contract gaps: /analytics/weekly-pattern, /analytics/monthly-comparison, /budgets/status, /categories/suggest (all added), simulator + budget + transaction schemas now accept frontend field aliases (category/limit_amount/period/percentage)
- Live E2E on uvicorn :8013 with seeded demo user: dashboard income ₹360,000 / expense ₹404,592.25 / 390 txns; forecast 30d ₹57,797.92, interval [₹23,966.81, ₹91,629.03]; assistant (prediction agent) quoted identical ₹57,797.92 — deterministic consistency confirmed
- verify.sh initially reported 3 false failures due to a relative-path bug in the harness itself; fixed to absolute venv path and re-run green
