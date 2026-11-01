# Stage 3 Engineering Report — Health Score v2, Digital Twin, Cash-Flow v2

Date: 2026-11-01. Scope: Stage 3 only (approved). Stage 4 not started.

## What was built

### Feature B — Financial Health Score v2 (`advanced_v2`)
- Sixth component added: **goal progress** (average funded % of the
  user's savings goals, direct transparent mapping). Weights rebalanced
  into a single config object `HEALTH_WEIGHTS` (savings .25, budget .20,
  stability .20, anomaly .10, buffer .10, goals .15), returned with
  every score. Methodology documented in `docs/HEALTH_SCORE.md`.
- **Data coverage & confidence**: components computed from missing data
  keep the neutral 60 from v1 but are now flagged `data_backed: false`;
  responses carry `data_coverage_percent` (weighted share backed by real
  data), `confidence` (high/medium/low), and the **"not a credit score"**
  disclaimer. Users are never silently penalised for missing data.
- **Snapshots & history**: reading the score stores one snapshot per
  user per day (new table `health_score_snapshots`, migration 003).
  `GET /analytics/health-score/history` returns snapshots plus a change
  explanation: total delta and the component whose weighted contribution
  moved most. Scores are reproducible from stored components (tested).
- Debt dimension deliberately deferred: no user-supplied debt data
  source exists; rationale documented in `HEALTH_SCORE.md`.
- Demo data: **68.5 (B)**, coverage 65%, confidence medium (v1 was 70.7
  under the old weights — the change is the versioned methodology, see
  HEALTH_SCORE.md).

### Feature A — Personal Financial Digital Twin
- New `app/intelligence/profile.py`, served by the engine as
  `GET /intelligence/profile` (typed envelope) and a new **Profile page**
  in the UI (sidebar: Profile).
- Contents: income patterns (average, regularity CV + label, detected
  primary source with typical amount/day, all sources with shares),
  expense patterns (top categories with monthly averages and shares,
  discretionary share), spending consistency, recurring obligations,
  savings behavior, current-month budget adherence, goals, deterministic
  **risk indicators with evidence**, **savings opportunities**, predicted
  patterns (ML expense estimate + observed income average, labelled
  assumed), and explicit **data gaps**. No new tables; nothing invented —
  an empty account gets `insufficient_data` with labelled gaps.
- Demo data: avg monthly income ₹90,641.67 (= summary total ÷ 6, exact),
  primary source TechCorp India ₹85,000 around day 1, consistency
  "moderate" (CV 0.202), subscriptions ₹5,166/mo (5.7% of income),
  risks flagged: buffer, income concentration; gaps: budgets, goals.
- Pattern *correction* UI arrives with Stage 4 overrides, per the audit.

### Feature C — Cash-Flow Forecasting v2 (dated timeline)
- New `cashflow_timeline` in `advanced.py`, via engine, at
  `GET /analytics/cashflow-timeline?horizon_days=30|60|90` (other values
  → 422), plus a **Cash-flow timeline card on the Predictions page**
  (horizon toggle, balance curve, event list, assumptions).
- Composition: income events from the detected monthly income pattern
  (labelled **assumed**) or user-scheduled recurring income
  (**confirmed**); obligation events from detected subscriptions,
  recurring groups and user-scheduled recurring expenses (pattern vs
  confirmed); plus a flat baseline daily discretionary spend =
  trailing-90d expense minus the obligations' run-rate (no double
  counting). Balances are **relative to today** (starting balance null,
  basis stated) because FinSight does not know the user's bank balance.
- Outputs: daily series, event list, lowest projected balance + date,
  first shortage date, end-of-month balance, totals. **Shortage
  semantics**: flagged only when the balance goes negative and is not
  restored by the next projected income — an overnight pre-payday dip is
  not counted (this refinement was added after probing showed day-one
  dips; documented in the response assumptions).
- Verified on three personas: healthy synthetic user → no shortage,
  projected net > 0; low-income user (₹8,000/mo vs ₹4,500/week recurring
  groceries) → shortage flagged; demo data → obligations ₹23,166 in 30
  days (rent ₹18,000 recurring + ₹5,166 subscriptions — exactly the
  subscription + recurring outputs), and a genuine projected shortage on
  Nov 23 because the trailing-90-day window (Aug–Oct) was the demo
  persona's heaviest spending period. That is the honest output of the
  stated basis, shown with its assumptions in the UI.

## Files created
- `backend/app/intelligence/profile.py`
- `backend/alembic/versions/003_health_score_snapshots.py`
- `frontend/src/app/(dashboard)/profile/page.tsx`
- `docs/HEALTH_SCORE.md`, `docs/STAGE3_REPORT.md`

## Files modified
- `backend/app/models/models.py` (HealthScoreSnapshot model)
- `backend/app/analytics/advanced.py` (health v2, snapshots/history,
  income-pattern helper, cash-flow timeline; version → `advanced_v2`)
- `backend/app/intelligence/engine.py` (profile + cashflow_timeline)
- `backend/app/api/v1/resources.py` (snapshot-on-read health endpoint,
  history, profile, timeline endpoints)
- `backend/tests/test_backend.py` (+4 Stage 3 tests; 1 existing
  assertion updated to the v2 component set — a deliberate, documented
  contract extension)
- `frontend/src/lib/api.ts` (health history, profile, timeline client +
  types), dashboard page (coverage/confidence/change/disclaimer on the
  health card, "(est.)" marks), predictions page (timeline card),
  sidebar (Profile link)

## Verification (all executed 2026-11-01)
- Backend pytest: **29 passed, 0 failed** (25 prior + 4 new).
- Frontend: Vitest **9/9**, tsc pass, production build pass (one ESLint
  unescaped-entities failure was caught by verify.sh and fixed).
- `scripts/verify.sh`: **0 failed stages**.
- Migrations: SQLite — upgrade 002 → 003 on an existing database, drift
  check clean, 16 tables. **PostgreSQL 16** — clean upgrade head, drift
  check clean, 003 downgrade/upgrade round-trip.
- Persona probes (demo / healthy / low-income / empty) as described
  above; profile values cross-checked against the summary endpoint.

## Known limitations
- Timeline baseline is a flat daily rate (documented assumption); it
  does not model weekday seasonality (Stage 6 behavior work).
- Snapshot-on-read means history accrues on days the score is viewed;
  a background daily job is a Stage 10 candidate.
- The dashboard's v1 cashflow card is unchanged (still served by
  `/ml/cashflow`); the v2 timeline lives on Predictions.
- No rendered-UI screenshot pass (browser cannot reach this VM's
  localhost — same constraint as Stage 2); API shapes, unit tests and
  builds verified instead.

## Remaining
Stage 4 — Subscription intelligence v2 + Financial Calendar
(`subscription_overrides`, `payment_reminders`) — awaiting approval.
