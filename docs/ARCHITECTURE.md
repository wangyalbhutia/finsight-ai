# FinSight AI — Architecture (Phase 1)

## 1. Inspection result
Greenfield workspace on 2026-10-31. No existing repo, dependencies, or working code to preserve.
Runtime available: Python 3.12.3, Node 24, npm 10. Stack chosen exactly as specified.

## 2. System architecture
```
Browser (Next.js, TS, Tailwind, Recharts)
   │  HTTPS, JWT Bearer (access) + rotating refresh
   ▼
FastAPI  ──► Analytics Service (deterministic, DB-backed)
   │     ├─► ML Package: categorization | forecasting | anomaly
   │     ├─► Agent Orchestrator ─► Analytics / Prediction / Anomaly / Recommendation agents
   │     │        └─► LLM Adapter (provider-independent, optional) — explains tool output only
   │     └─► Budget / Simulator / Reports services
   ▼
PostgreSQL 16 (prod) · SQLite (local dev/tests via DATABASE_URL fallback)
```
**Golden rule:** All numbers come from deterministic backend services. The LLM never invents
figures; agents pass structured tool results to it, and a deterministic template fallback
works with no LLM key at all.

## 3. Calculation rules (no double-counting)
- `income`: counts toward income. `expense`: counts toward expenditure.
- `transfer`: excluded from both income and expense totals (money moving between own accounts).
- `refund`: offsets expenditure in its category (reduces expense, never counted as income).
- Savings rate = (income − net expense) / income, guarded for income = 0.
- Money is `Decimal`/`NUMERIC(12,2)`, never float. Timestamps UTC.

## 4. ML design
- **Categorization:** TF-IDF (char+word n-grams) → Logistic Regression, merchant-rule fallback,
  confidence score, user corrections become new labelled examples.
- **Forecasting:** chronological split only (never shuffled). Moving average + Holt-Winters
  Exponential Smoothing baselines; backtest MAE/RMSE, MAPE only when actuals ≠ 0.
  Outputs 7d / 30d / month-end / per-category with intervals, `model_version`, `generated_at`.
- **Anomaly:** median/MAD robust z-score + Isolation Forest (≥20 txns), duplicate hash,
  category spike vs trailing median, unusual merchant. Language is "unusual", never "fraud".

## 5. Security
bcrypt hashing, JWT verified server-side on every protected route, user taken from token
(never from client-supplied `user_id`), per-query `user_id` scoping (IDOR-safe), refresh
tokens stored hashed + revoked on logout, Pydantic validation, parameterised SQLAlchemy
queries, CORS allow-list, rate limit on auth, safe CSV validation, secrets only in env.

## 6. Folder structure
As specified in the brief: `backend/app/{api/v1,core,models,schemas,services,analytics,ml,agents,integrations,tests}`
and `frontend/src/{app,components,hooks,lib,services,types}`.
