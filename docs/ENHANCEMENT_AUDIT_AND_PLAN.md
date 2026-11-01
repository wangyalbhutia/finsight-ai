# FinSight AI — Stage 1: Repository Audit & Enhancement Plan

Audit date: 2026-11-01. Method: full code/doc inspection, route/model/test
inventory, `scripts/verify.sh` execution, and live benchmarks at
1k / 10k / ~49k transactions (SQLite, this VM). Nothing below is assumed
from documentation alone; every status was checked against code or a
running measurement.

## 1. Current state (verified)

- **Verification suite today:** backend pytest **24/24 pass**, frontend
  tsc pass, production build pass, Alembic check pass, verify.sh
  **0 failed stages** (Docker stage skipped — Docker unavailable here).
- **Surface:** 71 API routes, 14 database tables, 13 frontend routes,
  24 backend tests + 5 frontend tests.
- **Docs:** ARCHITECTURE.md, DATABASE_AND_API.md, VERIFICATION.md,
  ADVANCED_FEATURES.md — accurate for what exists.

### Fully implemented (reuse, do not rebuild)
Auth with refresh rotation + reuse detection + logout denylist; user
isolation (tested); transactions CRUD with SQL search/pagination; CSV
import/export with dedup-hash idempotency and strict validation;
categories + ML/rule suggestion + auto-categorize; analytics (summary,
categories, trends, weekly pattern, monthly comparison, recurring) under
Phase-1 rules (Decimal, transfers excluded, refunds offset); ML
categorization (TF-IDF + logistic regression + rules); forecasting with
chronological split, naive/MA/ES comparison, MAE/RMSE/MAPE, honest
insufficient-data; anomaly detection (robust MAD z-score + Isolation
Forest + duplicates); budgets + status/alerts/recommendations; goals
CRUD; simulator (reduction, compare, affordability); monthly/yearly
reports with CSV/PDF export; agent orchestrator with specialist agents,
read-only tools, prompt-injection sanitisation, LLM fallback; advanced
pack (health score v1, smart insights, subscription detection, budget
forecast, cashflow v1); audit log on CSV import.

## 2. Performance measurements (the evidence for §9 work)

| Transactions | Summary | Dashboard | Smart insights | Forecast (at ~49k) |
|---:|---:|---:|---:|---:|
| 1,000 | 21 ms | 78 ms | 61 ms | — |
| 10,000 | 225 ms | 1,229 ms | 726 ms | — |
| ~49,000 | 1,436 ms | 6,756 ms | 4,105 ms | 3,874 ms |

Root cause: analytics loads **all** of a user's transactions into Python
(`_all()`), and composite endpoints repeat the load — dashboard runs
summary + breakdown + trends + recurring (4–5 full passes), insights
internally re-runs category breakdown + subscription detection + budget
forecast. Indexes already exist (user_id, date, category, merchant,
composite user+date). **Fix: SQL aggregation + a single shared data pass
in the Intelligence Engine (Stage 2). No new infrastructure needed yet.**

## 3. Architectural limitations

1. **Migration shim:** `alembic/versions/001_initial.py` calls
   `Base.metadata.create_all` — it is not a real versioned migration and
   cannot evolve a production schema. Any new table requires adopting a
   true baseline migration first (Stage 2 prerequisite).
2. `Base.metadata.create_all` also runs at app import in `main.py`
   (masks migration problems; keep for dev, gate for production).
3. No caching or background jobs — acceptable at current scale; forecast
   and imports are the first candidates if profiling demands it.
4. Rate limiter is in-memory per process (fine for one instance, wrong
   for multi-instance deploys).
5. Tokens stored in `localStorage` (XSS-sensitive tradeoff, documented).
6. Default dev `SECRET_KEY` in config/compose — must be overridden in
   production (already env-driven).
7. CSV import reads the whole upload into memory with **no size limit** —
   must be fixed before any statement-ingestion work (Stage 5 includes it).

## 4. Feature-by-feature plan

Format per feature: status → new work → files → DB → deps → complexity →
security → acceptance tests.

### §2 Central Financial Intelligence Engine — NEW (consolidation)
Status: logic exists but is spread across `analytics/service.py`,
`analytics/advanced.py`, `ml/*`. New: `app/intelligence/engine.py` facade
returning a typed envelope {kind: fact|forecast|assumption|recommendation,
data_freshness, model_version, generated_at, payload}; dashboard + agents
consume it; single data pass per request. Files: new engine module,
`resources.py`, `agents/*`, `api.ts`. DB: none. Deps: none. Complexity: M.
Security: engine is read-only and user-scoped. Acceptance: all 24 existing
tests pass unchanged; dashboard p95 at 10k txns < 400 ms in benchmark;
agents' numbers identical before/after (golden-response test).

### Feature A: Digital Twin — PARTIAL → build on engine
Ingredients exist (income/expense patterns, recurring, health, insights);
no unified profile object, endpoint, or UI, and no user-correction path.
New: `GET /intelligence/profile` (current profile, behavior history,
predicted patterns, risk indicators, savings opportunities) + profile
page + pattern-correction via subscription/category overrides (Stage 4).
DB: none initially (computed); snapshots come with Health v2. Complexity: M.
Security: profile is derived only from the user's records; every inferred
pattern is labelled with its evidence. Acceptance: profile values match
analytics endpoints exactly on demo data; insufficient-history profile
returns labelled gaps, not inventions.

### Feature B: Financial Health Score — EXISTS v1 → v2
Exists: 5 weighted components with explanations. Missing: confidence /
data-coverage, history + change explanations, goal-progress dimension,
debt dimension (only when user supplies it), configurable weights,
"not a credit score" labelling. New: snapshot on read (daily),
`GET /analytics/health-score/history`, coverage % = share of components
computed from real data vs neutral, weights in one config object.
DB: `health_score_snapshots`. Deps: none. Complexity: M. Security: none
new. Acceptance: score reproducible from stored components; history shows
delta with the component that moved most; user with no budgets/goals is
not penalised (neutral + coverage < 100% disclosed).

### Feature C: Cash-Flow Forecasting — EXISTS v1 → v2
Exists: 30-day income (trailing-90d average) + ML expense forecast + net.
Missing: 60/90-day horizons surfaced in UI, recurring-obligation schedule,
shortage detection, end-of-month balance, confirmed-vs-assumed labelling.
New: build a dated cash-flow timeline (salary pattern, detected
obligations, forecast daily expenses) → lowest projected balance + first
shortage date; account balance used only if the user maintains it.
Files: `advanced.py`/`engine`, predictions page. DB: none. Complexity: M.
Acceptance: on demo data, timeline obligations equal subscription +
recurring outputs; shortage flag triggers on a synthetic low-income user;
unconfirmed inflows labelled "assumed".

### Feature D: Adaptive Forecasting — PARTIAL
Exists: one chronological split comparing naive/MA/ES with MAE/RMSE/MAPE;
predictions store model_version + metrics. Missing: rolling-origin
evaluation, per-category evaluation, drift monitoring, XGBoost.
New: rolling-origin backtest (3 folds) in `ml/forecasting`, per-category
evaluation endpoint, drift = recent-fold vs older-fold MAE change.
XGBoost: **gated** — add only if it beats ES on rolling-origin for
profiles with ≥180 days of daily data; otherwise document the negative
result ( dependency ~200 MB is not justified by default). Complexity: M
(L if XGBoost lands). Acceptance: evaluation reproducible (fixed seeds),
selection never picks a model that loses to naive on the same folds.

### Feature E: Behavior Intelligence — PARTIAL → v2
Exists in insights: category spikes, concentration, large purchases,
subscription burden/price hikes. Missing: lifestyle inflation
(discretionary spend trend vs income trend, 3-month windows), micro-
transaction pattern (many small discretionary charges), subscription
creep (detected subscription cost by month), weekend uplift (weekly
pattern exists as data), merchant-preference shift, discretionary ratio.
New rules in the insights engine, each with evidence + comparison +
impact + suggested action + confidence/limits. DB: none. Complexity: M.
Acceptance: each new rule fires on a synthetic fixture built for it and
stays silent on a flat-spending fixture; no insight contains a number
that differs from the analytics endpoints.

### Feature F: Subscription Intelligence — EXISTS → v2 (user control)
Exists: detection, frequency, monthly/annual cost, price changes, next
expected date. Missing: confirm/edit/dismiss, duplicate detection
(same service billed via two merchant spellings), calendar view (→ G).
New: overrides applied on top of detection. DB: `subscription_overrides`
(user_id, merchant, status, custom_amount, custom_frequency). Complexity: S–M.
Security: overrides are user-scoped; detection remains "potential
subscription" wording until confirmed. Acceptance: dismissed merchant
never reappears; confirmed subscription shows as confirmed; duplicate
pair (e.g. "Netflix" / "NETFLIX.COM") flagged once.

### Feature G: Financial Calendar — MISSING
New: `GET /calendar/events?from&to` computing events from recurring
transactions, subscriptions (next dates), budget month boundaries,
salary pattern; manual reminders CRUD stored in DB: `payment_reminders`.
Frontend: new /calendar page (list + month grid), cash-flow overlay =
Stage-3 timeline. Deps: none. Complexity: M. Security: all user-scoped.
Acceptance: demo data produces rent on the 2nd, salary on the 1st,
Netflix on the 10th; manual reminder create/edit/delete round-trips;
events never include another user's data (isolation test).

### Feature H: Natural-Language Transaction Entry — MISSING (safe design)
New: stateless `POST /transactions/parse` (rule-based extractor: amount,
currency symbols ₹/Rs/$, type keywords, date words today/yesterday,
merchant/category via existing categoriser) → structured draft; frontend
shows editable preview; creation happens only through the existing
validated `POST /transactions` after explicit confirmation. Ambiguous
amount/date → draft flags the field instead of guessing. DB: none.
Deps: none. Complexity: M. Security: parsed text is data; parser is
deterministic (no LLM in the write path); injection strings in the text
cannot create fields. Acceptance: the three spec examples parse exactly;
"lunch with friends" (no amount) returns `needs_review` and creates
nothing; confirmation flow covered end-to-end.

### Feature I: Receipt OCR & Statement Intelligence — MISSING (stage it)
CSV statement import exists. New v1: PDF statements with a text layer
(`pdfplumber`), generic + UPI/bank-format row extraction, merchant
normalisation, same dedup + **preview-before-import** flow as H (nothing
auto-imports). Upload hardening pulled in here: size cap (5 MB), type
check, in-memory/temp processing with cleanup, import audit row (hash +
counts only, document itself never stored). OCR for images/scanned PDFs:
**deferred** — needs the tesseract binary + pytesseract and accuracy is
materially lower; revisit after v1. DB: `statement_imports` (audit only).
Deps: pdfplumber. Complexity: L. Security: documents treated as
untrusted; extracted instructions are inert data; per-user isolation on
staging. Acceptance: a generated HDFC-style PDF statement parses to the
same rows as its CSV twin; malformed/oversized files rejected with
reasons; re-import yields duplicates, not doubles.

### Feature J: Scenario Simulator — PARTIAL → v2
Exists: category reduction, compare (≤3), affordability. Missing:
income change, one-off shock expense, new recurring obligation, balance
trajectory comparison. New: `POST /simulator/trajectory` computing
month-by-month projected balance for base + scenario from engine
cash-flow assumptions, with assumptions listed in the response.
Simulations never write transactions (already true). DB: none.
Complexity: M. Acceptance: scenario math reconciles with affordability
outputs on the same fixture; base trajectory matches cash-flow v2.

### §4 Agents & Financial Memory — PARTIAL
Exists: orchestrator + specialists + advanced intents, read-only tools,
sanitisation, fallback, stored conversations. Missing: curated Financial
Memory (structured, user-editable/deletable, versioned), proactive
briefings, result caching. New: `user_memories` table + CRUD endpoints +
Settings UI; briefing generator (top actionable insight, deduped against
the last briefing, dismissible) delivered as in-app `notifications`
(table) — email/push need an external provider decision, out of scope
until chosen; engine-level memoisation per (user, data-version).
Complexity: M–L. Security: memory is user-owned, never shared across
users, and the assistant must disclose stored memories on request.
Acceptance: memory CRUD + isolation tests; briefing does not repeat an
unchanged insight twice; injection fixture still passes with memory on.

### §5 UX — PARTIAL
Exists: responsive layout, dark/light, skeletons, empty/error states.
Missing: onboarding wizard, dashboard personalisation (widget show/hide
+ order, persisted in `user_memories`-backed preferences), custom date
ranges (backend summary takes year/month today; add start/end params),
goal forecasts (reuse affordability math), challenges. Challenges are
**lowest priority** and must avoid unhealthy incentives (no spend-to-win
mechanics). Complexity: M (onboarding+personalisation), S (date ranges),
M (goal forecasts). Acceptance: preferences persist across sessions;
onboarding can load the existing demo dataset as sample data; keyboard
navigation + focus states checked on new pages.

### §6 India-specific — PARTIAL
Exists: INR-first formatting, rent/recharge/utility merchants in
categoriser rules, education category, multi-currency separation.
New with Stage 5: UPI statement formats (PhonePe/GPay/Paytm CSV/PDF
layouts) in the statement parser, merchant normalisation dictionary
(UPI handles → merchant names), preset categories (Hostel, Mess Fees,
Allowance income type). No SMS/bank access (out of scope, as specified).
Complexity: bundled into Stage 5 + S. Acceptance: UPI-format fixture
imports with normalised merchants and zero silent currency mixing.

### §7 Technical — evaluated, mostly DEFER
Justified now: SQL aggregation (Stage 2, measured), upload limits
(Stage 5), structured audit expansion (imports + memory changes),
real migrations (Stage 2). Deferred with reasons: Redis/Celery (no
measured need at ≤50k txns after SQL fix), semantic search (keyword SQL
search is adequate; embeddings add cost without a measured gap), drift
monitoring (lands with Feature D as fold-comparison, no infra),
microservices (explicitly out). Backup strategy: document SQLite/Postgres
dump procedure in README (S, Stage 10).

### §8 Security — gaps to close
1. Upload size/type limits (Stage 5, or earlier as a hotfix).
2. Account data export (full JSON/CSV) + account deletion endpoints —
   MISSING today; add in Stage 7/10 (S).
3. Production checklist: SECRET_KEY override, create_all gate (Stage 2).
4. All new write paths keep the confirm-first rule (H, I) and
   user-isolation tests are mandatory per feature (Definition of Done).

## 5. New database tables (total across all stages)
`health_score_snapshots`, `subscription_overrides`, `payment_reminders`,
`user_memories`, `notifications`, `statement_imports` (audit only).
All require the Stage-2 migration baseline first.

## 6. Recommended sequence (dependency-aware)
1. **Stage 2** — Intelligence Engine + SQL aggregation + migration
   baseline. (Unlocks everything; fixes the measured bottleneck.)
2. **Stage 3** — Health Score v2 + Digital Twin + Cash-Flow v2.
3. **Stage 4** — Subscriptions v2 + Financial Calendar.
4. **Stage 5** — NL entry + statement ingestion (incl. UPI) + upload
   hardening.
5. **Stage 6** — Behavior intelligence v2 + adaptive ML evaluation.
6. **Stage 7** — Financial Memory + proactive briefings + data
   export/deletion.
7. **Stage 8** — Simulator v2 trajectories + Goals v2.
8. **Stage 9** — Onboarding + dashboard personalisation + date ranges.
9. **Stage 10** — Perf regression tests (10k), security pass, Docker/
   Postgres verification on a capable machine, docs.

Each stage ships only when its acceptance tests pass and verify.sh is
green; existing behavior is the regression baseline (24 backend + 5
frontend tests today).
