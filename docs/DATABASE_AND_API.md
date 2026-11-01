# FinSight AI — Database Schema & API Plan (Phase 1)

## Database schema (all tables have id, created_at UTC; user-owned tables have user_id FK + index)
| Table | Key fields |
|---|---|
| users | email (unique), hashed_password, full_name, currency='INR', is_active |
| refresh_tokens | user_id FK, token_hash, expires_at, revoked_at |
| accounts | user_id FK, name, type, balance NUMERIC(12,2) |
| categories | user_id FK (nullable = system), name, type, icon, is_system |
| transactions | user_id FK, account_id FK, category_id FK, type enum(income/expense/transfer/refund), amount NUMERIC(12,2), merchant, description, notes, txn_date, is_recurring, dedup_hash (indexed) |
| budgets | user_id FK, category_id FK nullable, month, amount_limit, alert thresholds |
| recurring_transactions | user_id FK, frequency, next_run_date, template fields |
| financial_goals | user_id FK, name, target_amount, current_amount, deadline |
| predictions | user_id FK, horizon_days, forecast JSON, mae/rmse/mape, model_version, generated_at |
| anomaly_alerts | user_id FK, transaction_id FK, kind, severity, reason, score, status(open/acknowledged/dismissed) |
| ai_conversations / ai_messages | user_id FK, role, content, tool_calls JSON |

## API plan — base `/api/v1`, all except auth/health require JWT
- `GET /health`
- Auth: `POST /auth/register|login|refresh|logout`, `GET /auth/me`
- Transactions: `GET|POST /transactions`, `GET|PUT|DELETE /transactions/{id}`, `POST /transactions/import` (CSV → accepted/rejected/duplicates), `GET /transactions/export`
- Categories: `GET|POST /categories`, `DELETE /categories/{id}`, `POST /categories/suggest` (ML)
- Analytics: `GET /analytics/summary|trends|categories|monthly-comparison|recurring` (range params)
- ML: `POST /ml/forecast` + `GET /ml/forecast/latest`, `GET /ml/evaluation`, `POST /ml/anomalies/scan`, `GET /anomalies`, `PATCH /anomalies/{id}` (ack/dismiss)
- Budgets: `GET|POST /budgets`, `PUT|DELETE /budgets/{id}`, `GET /budgets/status` (utilisation + alerts + overrun forecast)
- Assistant: `POST /assistant/chat`, `GET /assistant/conversations`
- Simulator: `POST /simulator` (scenarios[])
- Reports: `GET /reports/monthly|yearly`, `GET /reports/export?format=csv|pdf`

## Phase checklist
- [x] P1 Inspection + architecture + schema + API plan
- [x] P2 Scaffolding, Docker, Postgres/SQLite, env config
- [x] P3 Auth + Transactions + CSV
- [x] P4 Analytics + dashboard APIs
- [x] P5 ML: categorization, forecasting, anomaly
- [x] P6 Assistant + orchestrator + 4 agents
- [x] P7 Budgets + recommendations + simulator
- [x] P8 Reports CSV/PDF
- [x] P9 Tests, security, performance
- [x] P10 README, docs, deployment verification
