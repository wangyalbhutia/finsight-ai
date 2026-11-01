# FinSight AI — Advanced Features (Upgrade Pack)

All features below follow the approved Phase 1 rules: deterministic backend
calculations, Decimal money, transfers excluded from income/expense, refunds
offset expenses, and the LLM only explains tool outputs. Where data is
insufficient, endpoints say so instead of fabricating numbers.

## Financial Health Score — `GET /api/v1/analytics/health-score`
Weighted 0–100 score (grade A–E) from five transparent components, each
returned with its inputs: savings rate (30%), budget adherence (25%),
spending stability / monthly CV (20%), open anomaly alerts (15%), and
buffer months (10%). No budgets or <2 months of data → the affected
component is a labelled neutral 60, never a hidden guess.
UI: Dashboard card. Assistant: "What is my financial health score?"

## Smart Insights — `GET /api/v1/analytics/insights`
Rule engine over the user's real transactions: category spikes vs last
month (≥20% and ≥₹500), top-category concentration ≥30%, negative/strong
savings rate, subscription burden and price hikes, budget risk, unusually
large recent purchases vs the user's median expense, refunds recovered.
Every insight carries the numbers behind it (`metric`).
UI: Analytics page. Assistant: "Give me insights".

## Subscription Detection — `GET /api/v1/analytics/subscriptions`
Detects subscriptions from charge patterns alone: same merchant, ≥3
charges, regular cadence (weekly/monthly/quarterly/yearly), stable amount
(±20%). Reports monthly/annual cost, next expected charge date, and price
changes >2%. Rent is explicitly excluded (a bill, not a subscription).
UI: Analytics page. Assistant: "How much do I spend on subscriptions?"

## Budget Forecast — `GET /api/v1/budgets/forecast`
Projects each current-month budget to month-end from the daily run-rate:
projected month-end spend, projected utilisation, safe daily allowance,
and risk (low / medium / high / exceeded). Deterministic projection,
labelled as such.

## Cashflow Projection — `GET /api/v1/ml/cashflow?horizon_days=30`
Projected income (trailing-90-day average rate) minus projected expenses
(the ML forecasting module, with its honest insufficient-data flag and
prediction interval) = projected net and savings rate for the horizon.
UI: Dashboard card.

## Affordability Planner — `POST /api/v1/simulator/afford`
Body: `{item_name, cost, months}`. Uses the average monthly surplus over
the last 3 calendar months to compute required monthly saving, feasibility,
shortfall, months needed at the current surplus, and the projected
affordable date. UI: Simulator page. Assistant: "Can I afford a phone for
₹60,000 in 6 months?" (also understands "60k" / "1 lakh").

## ML Auto-Categorize — `POST /api/v1/transactions/{id}/auto-categorize`
Runs the existing TF-IDF + logistic-regression categoriser (with merchant
rules) on one of the user's own transactions and applies the suggestion
only when confidence ≥ 0.50; otherwise it returns the suggestion without
changing data.

## Assistant integration
The agent router gained four grounded intents — health, subscriptions,
affordability, insights — all backed by the deterministic tools above and
listed in the chat response's `tools_used`. Financial writes remain
disabled; every new endpoint is read-only except auto-categorize, which
only touches the requesting user's own transaction.
