# Financial Health Score — Methodology (v2, Stage 3)

The health score is a deterministic, explainable summary of a user's own
transaction history, computed by the Intelligence Engine
(`app/analytics/advanced.py::financial_health_score`, version
`advanced_v2`). **It is not a credit score** and not a universal measure
of financial well-being; the disclaimer travels with every API response
and is shown in the UI.

## Components and weights

Weights live in one config object (`HEALTH_WEIGHTS`) and are returned
with every score:

| Component | Weight | What it measures |
|---|---:|---|
| Savings rate | 25% | Overall savings rate mapped onto 0–100 (`50 + rate × 2.5`, clamped). |
| Budget adherence | 20% | This month's average budget utilisation; full marks at ≤80%, decaying above. |
| Spending stability | 20% | Coefficient of variation of net monthly spending over observed months. |
| Anomaly control | 10% | Open anomaly alerts (high −15, medium −8, low −3 each). |
| Buffer | 10% | Net balance expressed in months of average spending. |
| Goal progress | 15% | Average funded percentage across the user's savings goals (direct, transparent mapping). |

Grades: A ≥ 80, B ≥ 65, C ≥ 50, D ≥ 35, E below.

## Missing data is never punished silently

Where data is missing (no budgets this month, fewer than two months of
spending, no goals), the component takes a **neutral 60** and is flagged
`data_backed: false`. Every response includes:

- `data_coverage_percent` — the weighted share of components computed
  from real data (e.g. 65% when budgets and goals are absent);
- `confidence` — high ≥ 90% coverage, medium ≥ 60%, low below;
- per-component `note` (the exact inputs) and `data_backed` flag.

The UI marks estimated components "(est.)" next to the score.

## History and change explanations

Reading the score stores one snapshot per user per day
(`health_score_snapshots`, migration `003_health_snapshots`).
`GET /analytics/health-score/history` returns the snapshots plus a change
explanation versus the previous reading: the total delta and the
component whose *weighted* contribution moved most — so "why did my
score change?" is answered from stored components, reproducibly: a score
can always be recomputed as Σ(component score × weight).

## Debt dimension

There is deliberately no debt component in v2: FinSight has no
user-supplied debt/liability data source yet, and inventing one would
violate the no-fabrication rule. When a supply path exists, the component
will be added to `HEALTH_WEIGHTS` (renormalised) with the same
neutral-when-missing treatment.

## Demo-data reference (verified 2026-11-01)

Demo dataset (395 transactions): score **68.5, grade B**, coverage **65%**
(no budgets, no goals on that account), confidence **medium**. The v1
score on the same data was 70.7; the difference is the v2 weight
rebalance plus the new goal-progress component at neutral — methodology
changes are versioned (`advanced_v2`), never silent.
