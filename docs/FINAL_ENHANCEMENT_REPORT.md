# FinSight AI — Enhancement Programme: Final Report (Stages 4–10)

Completed 2026-11-01 in one accelerated push at the user's request
(submission deadline), following the Stage 1 audit plan. Stages 1–3 are
documented in `ENHANCEMENT_AUDIT_AND_PLAN.md`, `STAGE2_REPORT.md` and
`STAGE3_REPORT.md`. Everything below is verified by the automated suite:
**backend pytest 35/35, frontend tsc + production build pass,
`scripts/verify.sh` exit 0 (0 failed stages).**

## Stage 4 — Subscription intelligence v2 + Financial Calendar
- `subscription_overrides` table (migration 004): users can **confirm,
  edit or dismiss** detected subscriptions. Detection is always labelled
  **"potential"** until confirmed.
- Merchant normalisation (`merchant_key`): "Netflix", "NETFLIX.COM" and
  "Netflix Pvt Ltd" are one identity; duplicate spellings merge into a
  single entry with `also_seen_as` shown. A dismissed merchant never
  reappears; removing an override restores it as a potential detection.
- **Financial Calendar** (`GET /calendar/events`, `/calendar` page with
  month grid): salary pattern (assumed), subscriptions, recurring
  charges, user-scheduled recurring entries (confirmed), budget resets,
  goal deadlines and user **payment reminders** (CRUD,
  `payment_reminders`). Monthly items project by their detected
  day-of-month so a 30.5-day median interval cannot drift an event off
  its real day. Acceptance on the demo data: salary Nov 1, rent Nov 2,
  Netflix Nov 10 — asserted in tests.

## Stage 5 — Natural-language entry + statement ingestion
- `POST /transactions/parse`: deterministic rule-based extraction
  (amount, currency, type, date, merchant, payment method, ML category)
  returning a **draft only** — nothing is written until the user reviews
  and confirms through the normal validated create endpoint. Fields that
  cannot be extracted are listed in `ambiguous_fields`; the parser never
  guesses an amount. Spec examples verified: "Spent ₹250 on lunch today
  using cash" and "Received ₹15,000 as monthly allowance".
- `POST /transactions/import-statement`: bank/UPI statement CSVs
  (split Debit/Credit columns, multiple date formats, `UPI/NAME/…`
  merchant extraction) flow through the **same validation + dedup
  pipeline** as the plain CSV import; a `statement_imports` audit row
  stores counts and filename only (migration 005). Re-import is fully
  deduplicated.
- `POST /transactions/receipt-parse`: OCR → draft fields via tesseract
  when the engine is installed on the server; the image is never stored.
  Where tesseract is absent the endpoint returns an honest 503 instead
  of fabricating a parse. (The build VM's package mirror was unavailable,
  so OCR could not be exercised end-to-end there.)
- Upload hardening (audit finding): 5 MB hard limit enforced on all
  import endpoints.

## Stage 6 — Behaviour intelligence + adaptive ML evaluation
- New deterministic insight detectors, each carrying `evidence` and a
  `suggested_action`: **lifestyle inflation** (discretionary spend,
  last 90d vs prior 90d), **micro-transaction clusters** (≥25 purchases
  under ₹200 in 30 days), **weekend spending share**, **recurring-charge
  creep**.
- Forecasting evaluation is now **rolling-origin** (multiple chronological
  origins, averaged MAE/RMSE, best model selected on evidence) and
  **per-category** (`GET /ml/evaluation` → `rolling_origin`,
  `per_category`). Categories with too little history are reported as
  insufficient, never scored on noise. Chronological splits only — no
  shuffling, no leakage.

## Stage 7 — Financial Memory, briefings, data rights
- `user_memories` (migration 006): preferences, **merchant corrections**,
  life events, notes — visible and deletable on the Profile page. A saved
  merchant correction overrides the ML categoriser (confidence 1.0,
  source "your saved correction").
- **Proactive briefings** (`notifications`): generated deterministically
  from budget-forecast risk, warning insights and goal milestones;
  deduplicated per week; shown on the dashboard with mark-read.
- **Data export** (`GET /account/export`, one JSON with everything) and
  **account deletion** (`DELETE /account`, requires the literal
  confirmation `DELETE`; removes every user-owned row, then the user).

## Stage 8 — Simulator v2 + Goals v2
- `POST /simulator/trajectory`: month-by-month cumulative trajectory,
  baseline (trailing-6-month averages) vs scenario (category cut %, extra
  monthly savings, income change %, one-off expense), with every
  assumption listed and balances labelled relative-to-today.
- `GET /goals/{id}/forecast`: months-to-goal at the recent average
  monthly surplus, projected completion date, required monthly
  contribution for the deadline, on-track/behind status. With no
  positive surplus it returns `cannot_project` rather than inventing a
  date. Goals UI (create/list/delete/forecast) added to the Budgets page.

## Stage 9 — Onboarding, personalisation, challenges
- `/onboarding` guided setup: name + currency preferences, salary
  schedule (Calendar), first budget, first goal, import routes. A
  dashboard banner invites new (zero-transaction) users into it.
- Dashboard personalisation: widget visibility toggles (health, briefing,
  cashflow, challenges) persisted in the browser; summary month filter
  (all-time or any of the last 12 months, server-side via
  `/analytics/summary?year&month`).
- `GET /challenges`: weekly challenges computed from the user's own last
  week (top-category −10% with live progress, micro-purchase pause,
  surplus +5% nudge) rendered as a dashboard card.

## Stage 10 — Performance, security, verification
- Benchmark (49k transactions, current code): summary 21 ms,
  dashboard 372 ms / 0.9 MB, insights 760 ms, forecast 146 ms —
  vs 19.1 s / 108 MB for the dashboard before Stage 2. Insights now runs
  ~20 constant-count SQL aggregate queries (Stage 6 detectors); no
  endpoint loads transaction rows into Python.
- Security checks: every new endpoint is user-scoped and covered by
  isolation tests (calendar reminders, goal forecasts, memories,
  notifications, account deletion); upload size limits on all imports;
  statement audit stores no contents; receipt images are never stored;
  account deletion requires an explicit confirmation string.
- Migrations 001→006 verified on clean SQLite incl. `alembic check`
  (no drift) and a downgrade/upgrade round-trip. 001–003 were verified
  on real PostgreSQL 16 in Stages 2–3; 004–006 are additive
  create-table migrations in the same style, SQLite-verified (the VM
  could not reinstall PostgreSQL — broken package mirror — so PG was
  not re-run for 004–006; see MIGRATIONS.md).
- Known limits (unchanged, documented): Docker itself untested (not
  installed); no rendered-UI screenshot pass (browser agent cannot reach
  the VM's localhost) — UI verification is API contracts + unit tests +
  production builds; rate limiter is in-memory per process.

## Demo script for submission
1. `./run.sh`, sign in as `demo@finsight.ai / Demo@1234`.
2. Dashboard: briefing card, health score, challenges, cashflow; toggle
   widgets and the month filter.
3. Profile: the digital twin + "What FinSight remembers".
4. Analytics: confirm/edit/dismiss a subscription (dismiss Spotify —
   it never returns), behaviour insights with evidence.
5. Calendar: salary on the 1st, rent on the 2nd, Netflix on the 10th;
   add a payment reminder.
6. Transactions: quick-add "Spent ₹250 on lunch today using cash";
   import `finsight_demo_full.csv` or a bank statement CSV (all
   duplicates on re-import).
7. Simulator: run a trajectory; Budgets: forecast a goal's completion.
8. Predictions: rolling-origin + per-category model evaluation.
9. Settings → Your data: export JSON.
