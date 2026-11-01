"""
Advanced deterministic analytics (Phase 1 rules preserved):
- All numbers come from the same transaction data and Decimal-safe service
  layer. Nothing here invents figures; where data is missing the response
  says so (neutral component scores are labelled, forecasts reuse the ML
  module's honest insufficient-data contract).
- Features: financial health score, smart insights, subscription detection,
  budget month-end forecast, cashflow projection, affordability planner.
"""
import calendar
import json
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics.service import primary_currency, compute_summary, category_breakdown, daily_totals, _dec, D0
from app.models.models import Transaction, Budget, AnomalyAlert, FinancialGoal, HealthScoreSnapshot, RecurringTransaction, SubscriptionOverride

ADVANCED_VERSION = "advanced_v2"

# Stage 3 (Feature B): health-score weights live in ONE transparent config
# object. They are returned with every score so the methodology is fully
# visible in the product. Documented in docs/HEALTH_SCORE.md.
HEALTH_WEIGHTS = {
    "savings_rate": 0.25,
    "budget_adherence": 0.20,
    "spending_stability": 0.20,
    "anomaly_control": 0.10,
    "buffer": 0.10,
    "goal_progress": 0.15,
}
HEALTH_DISCLAIMER = ("This score is FinSight's own explainable summary of your transaction "
                     "history. It is not a credit score and not a universal measure of "
                     "financial well-being.")
NEUTRAL_SCORE = 60.0  # used where data is missing — disclosed via data_backed=False


def _month_key(d):
    return (d.year, d.month)


def _monthly_from_daily(daily_map):
    """Roll a {date: Decimal} daily-totals map up to {(year, month): Decimal}."""
    out = defaultdict(lambda: D0)
    for d, v in daily_map.items():
        out[_month_key(d)] += v
    return out


def _budget_spent_sql(db, user_id, cur, budget, year, month):
    """Month spend for one budget via two SQL SUMs (expenses minus refunds)."""
    from app.analytics.service import _range
    start, end = _range(year, month)
    spent = D0
    for type_, sign in (("expense", 1), ("refund", -1)):
        q = db.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == user_id, Transaction.type == type_,
            func.coalesce(Transaction.currency, "INR") == cur,
            Transaction.date >= start, Transaction.date < end)
        if budget.category_name and budget.category_name != "Overall":
            q = q.filter(Transaction.category_name == budget.category_name)
        spent += sign * _dec(q.scalar() or 0)
    return max(D0, spent)


# ---------------------------------------------------------------- health score
def financial_health_score(db: Session, user_id: int):
    """Weighted 0-100 score from five transparent components. Each component
    returns its inputs so the UI/assistant can explain the score."""
    cur = primary_currency(db, user_id)
    summary = compute_summary(db, user_id)
    if summary["transaction_count"] == 0:
        return {"score": None, "grade": None, "insufficient_data": True,
                "message": "Add transactions to compute a financial health score.", "components": {},
                "version": ADVANCED_VERSION, "currency": cur}

    # 1) savings rate (30%)
    rate = float(summary["savings_rate"])
    savings_score = max(0.0, min(100.0, 50.0 + rate * 2.5))

    # 2) budget adherence (25%) — neutral 60 when the user has no budgets
    today = date.today()
    budgets = db.query(Budget).filter(Budget.user_id == user_id, Budget.month == today.month, Budget.year == today.year).all()
    if budgets:
        utils = []
        for b in budgets:
            spent = _budget_spent_sql(db, user_id, cur, b, today.year, today.month)
            utils.append(float(spent) / float(b.amount) * 100 if b.amount else 0.0)
        avg_util = sum(utils) / len(utils)
        budget_score = max(0.0, min(100.0, 100.0 - max(0.0, avg_util - 80.0) * 1.5))
        budget_note = f"Average budget utilisation this month: {avg_util:.0f}% across {len(budgets)} budget(s)."
    else:
        budget_score, avg_util = 60.0, None
        budget_note = "No budgets set for this month — neutral score. Create budgets to make this component real."

    # 3) spending stability (20%) — coefficient of variation of monthly spend
    monthly_exp = _monthly_from_daily(daily_totals(db, user_id, cur, "expense"))
    refunds = _monthly_from_daily(daily_totals(db, user_id, cur, "refund"))
    net_monthly = [float(monthly_exp[k] - refunds.get(k, D0)) for k in sorted(monthly_exp)]
    if len(net_monthly) >= 2 and statistics.mean(net_monthly) > 0:
        cv = statistics.pstdev(net_monthly) / statistics.mean(net_monthly)
        stability_score = max(0.0, min(100.0, 100.0 - max(0.0, cv - 0.15) / 0.45 * 100.0))
        stability_note = f"Monthly spending variation (CV) is {cv:.2f} over {len(net_monthly)} month(s)."
    else:
        cv, stability_score = None, 60.0
        stability_note = "Less than two months of spending — neutral score."

    # 4) anomaly control (15%) — open, unreviewed alerts drag the score
    open_alerts = db.query(AnomalyAlert).filter(
        AnomalyAlert.user_id == user_id, AnomalyAlert.status == "open").all()
    penalty = sum(15 if a.severity == "high" else 8 if a.severity == "medium" else 3 for a in open_alerts)
    anomaly_score = max(0.0, 100.0 - penalty)
    anomaly_note = f"{len(open_alerts)} open anomaly alert(s) awaiting review."

    # 5) buffer (10%) — net balance vs average monthly expense, in months
    avg_month_exp = (sum(net_monthly) / len(net_monthly)) if net_monthly else 0.0
    cover = (float(summary["net_balance"]) / avg_month_exp) if avg_month_exp > 0 else 0.0
    buffer_score = max(5.0, min(100.0, 30.0 + cover * 23.33))
    buffer_note = f"Net balance covers about {cover:.1f} month(s) of average spending."

    # 6) goal progress (15%) — Stage 3: real only when the user has goals;
    # score is the average funded percentage (transparent, no soft mapping).
    goals = db.query(FinancialGoal).filter(FinancialGoal.user_id == user_id).all()
    if goals:
        progresses = []
        for g in goals:
            target = float(g.target_amount or 0)
            progresses.append(min(100.0, float(g.current_amount or 0) / target * 100.0) if target > 0 else 0.0)
        goal_score = sum(progresses) / len(progresses)
        goal_note = f"{len(goals)} goal(s) are on average {goal_score:.0f}% funded."
        goal_backed = True
    else:
        goal_score, goal_backed = NEUTRAL_SCORE, False
        goal_note = "No savings goals yet — neutral score. Create a goal to make this component real."

    components = {
        "savings_rate": {"score": round(savings_score, 1), "weight": HEALTH_WEIGHTS["savings_rate"], "note": f"Savings rate is {rate:.2f}%.", "data_backed": True},
        "budget_adherence": {"score": round(budget_score, 1), "weight": HEALTH_WEIGHTS["budget_adherence"], "note": budget_note, "data_backed": bool(budgets)},
        "spending_stability": {"score": round(stability_score, 1), "weight": HEALTH_WEIGHTS["spending_stability"], "note": stability_note, "data_backed": len(net_monthly) >= 2},
        "anomaly_control": {"score": round(anomaly_score, 1), "weight": HEALTH_WEIGHTS["anomaly_control"], "note": anomaly_note, "data_backed": True},
        "buffer": {"score": round(buffer_score, 1), "weight": HEALTH_WEIGHTS["buffer"], "note": buffer_note, "data_backed": bool(net_monthly)},
        "goal_progress": {"score": round(goal_score, 1), "weight": HEALTH_WEIGHTS["goal_progress"], "note": goal_note, "data_backed": goal_backed},
    }
    total = sum(c["score"] * c["weight"] for c in components.values())
    grade = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D" if total >= 35 else "E"
    weakest = min(components.items(), key=lambda kv: kv[1]["score"])
    # Data coverage: weighted share of components computed from real data.
    coverage = round(100.0 * sum(c["weight"] for c in components.values() if c["data_backed"]), 1)
    confidence = "high" if coverage >= 90 else "medium" if coverage >= 60 else "low"
    return {"score": round(total, 1), "grade": grade, "insufficient_data": False,
            "components": components, "weakest_component": weakest[0],
            "weights": HEALTH_WEIGHTS, "data_coverage_percent": coverage,
            "confidence": confidence, "disclaimer": HEALTH_DISCLAIMER,
            "currency": cur, "version": ADVANCED_VERSION}


def snapshot_health_score(db: Session, user_id: int, result: dict):
    """Persist today's reading (one per user per day) so score changes can
    be explained later. Derived data only — never touches transactions."""
    if not result or result.get("insufficient_data") or result.get("score") is None:
        return None
    today = date.today()
    row = db.query(HealthScoreSnapshot).filter(
        HealthScoreSnapshot.user_id == user_id,
        HealthScoreSnapshot.snapshot_date == today).first()
    if row is None:
        row = HealthScoreSnapshot(user_id=user_id, snapshot_date=today)
        db.add(row)
    row.score = float(result["score"])
    row.grade = result["grade"]
    row.components = json.dumps(result["components"])
    row.data_coverage_percent = float(result.get("data_coverage_percent") or 0)
    row.currency = result.get("currency") or "INR"
    db.commit()
    db.refresh(row)
    return row


def health_score_history(db: Session, user_id: int, limit: int = 90):
    """Snapshots newest-first, plus a change explanation vs the previous
    reading: total delta and the component whose weighted contribution
    moved most (the honest 'why did my score change' answer)."""
    rows = db.query(HealthScoreSnapshot).filter(
        HealthScoreSnapshot.user_id == user_id).order_by(
        HealthScoreSnapshot.snapshot_date.desc()).limit(limit).all()
    snaps = [{"date": r.snapshot_date.isoformat(), "score": r.score, "grade": r.grade,
              "data_coverage_percent": r.data_coverage_percent, "currency": r.currency,
              "components": json.loads(r.components)} for r in rows]
    change = None
    if len(snaps) >= 2:
        cur_s, prev_s = snaps[0], snaps[1]
        delta = round(cur_s["score"] - prev_s["score"], 1)
        movers = []
        for name, comp in cur_s["components"].items():
            prev_comp = prev_s["components"].get(name)
            if prev_comp is not None:
                movers.append((name, (comp["score"] - prev_comp["score"]) * comp["weight"]))
        biggest = None
        if movers:
            name, weighted_delta = max(movers, key=lambda kv: abs(kv[1]))
            if abs(weighted_delta) >= 0.05:
                biggest = {"component": name, "weighted_delta": round(weighted_delta, 2),
                           "direction": "improved" if weighted_delta > 0 else "declined"}
        change = {"delta": delta, "since": prev_s["date"], "biggest_mover": biggest,
                  "explanation": (f"Score moved {delta:+.1f} since {prev_s['date']}"
                                  + (f"; the biggest driver was {biggest['component'].replace('_', ' ')} ({biggest['direction']})." if biggest else "."))}
    return {"snapshots": snaps, "count": len(snaps), "change": change,
            "disclaimer": HEALTH_DISCLAIMER}


# ------------------------------------------------------------- subscriptions
def detect_subscriptions(db: Session, user_id: int):
    """Detect subscriptions from real charge patterns: same merchant charged
    at a regular cadence (>=3 charges, stable amount). No external data."""
    cur = primary_currency(db, user_id)
    # Stage 2: only merchants with >=3 charges can be subscriptions — filter
    # in SQL and load columns (not full ORM rows) for just those merchants.
    candidates = [m for (m,) in db.query(Transaction.merchant).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.category_name != "Rent", Transaction.merchant != "",
        Transaction.merchant.isnot(None)
    ).group_by(Transaction.merchant).having(func.count(Transaction.id) >= 3).all()]
    by_merchant = defaultdict(list)
    if candidates:
        rows = db.query(Transaction.merchant, Transaction.amount, Transaction.date,
                        Transaction.category_name, Transaction.is_recurring).filter(
            Transaction.user_id == user_id, Transaction.type == "expense",
            func.coalesce(Transaction.currency, "INR") == cur,
            Transaction.merchant.in_(candidates)).order_by(Transaction.date).all()
        for merchant, amount, d, cat, rec in rows:
            if (merchant or "").strip():
                by_merchant[merchant.strip()].append(
                    {"amount": amount, "date": d, "category_name": cat, "is_recurring": rec})
    subs = []
    for merchant, charges in by_merchant.items():
        if len(charges) < 3:
            continue
        charges = sorted(charges, key=lambda t: t["date"])
        gaps = [(charges[i + 1]["date"] - charges[i]["date"]).days for i in range(len(charges) - 1)]
        med_gap = statistics.median(gaps)
        if med_gap <= 0 or not all(abs(g - med_gap) <= max(4, med_gap * 0.35) for g in gaps):
            continue
        amounts = [float(t["amount"]) for t in charges]
        med_amt = statistics.median(amounts)
        if med_amt <= 0 or (max(amounts) - min(amounts)) / med_amt > 0.20:
            continue
        if 25 <= med_gap <= 35:
            freq, per_month = "monthly", 1.0
        elif 6 <= med_gap <= 8:
            freq, per_month = "weekly", 30.0 / 7.0
        elif 350 <= med_gap <= 380:
            freq, per_month = "yearly", 1.0 / 12.0
        elif 80 <= med_gap <= 100:
            freq, per_month = "quarterly", 1.0 / 3.0
        else:
            continue
        monthly_cost = med_amt * per_month
        first, last = amounts[0], amounts[-1]
        change_pct = round((last - first) / first * 100, 2) if first else 0.0
        subs.append({
            "merchant": merchant, "category_name": charges[-1]["category_name"],
            "frequency": freq, "charges": len(charges), "average_amount": round(med_amt, 2),
            "monthly_cost": round(monthly_cost, 2), "annual_cost": round(monthly_cost * 12, 2),
            "last_charge_date": charges[-1]["date"].isoformat(),
            "typical_day_of_month": int(statistics.median([c["date"].day for c in charges])),
            "next_expected_date": (charges[-1]["date"] + timedelta(days=int(round(med_gap)))).isoformat(),
            "price_change_percent": change_pct if abs(change_pct) > 2 else 0.0,
            "flagged_recurring": any(bool(t["is_recurring"]) for t in charges),
            "method": "pattern_detection",
        })
    # ---- Stage 4 (Feature F): duplicate merge + user overrides ----
    merged = {}
    for sub in subs:
        key = merchant_key(sub["merchant"])
        sub["merchant_key"] = key
        sub["status"] = "potential"  # detection is never presented as fact
        sub["also_seen_as"] = []
        if key in merged:
            keep = merged[key]
            keep["also_seen_as"].append(sub["merchant"])
            keep["monthly_cost"] = round(keep["monthly_cost"] + sub["monthly_cost"], 2)
            keep["annual_cost"] = round(keep["monthly_cost"] * 12, 2)
            keep["charges"] += sub["charges"]
            if sub["next_expected_date"] < keep["next_expected_date"]:
                keep["next_expected_date"] = sub["next_expected_date"]
        else:
            merged[key] = sub
    subs = list(merged.values())

    overrides = {o.merchant_key: o for o in db.query(SubscriptionOverride).filter(
        SubscriptionOverride.user_id == user_id).all()}
    visible = []
    for sub in subs:
        ov = overrides.get(sub["merchant_key"])
        if ov is not None:
            if ov.status == "dismissed":
                continue  # a dismissed merchant never reappears
            sub["status"] = "confirmed"
            if ov.custom_amount is not None:
                sub["average_amount"] = round(float(ov.custom_amount), 2)
            if ov.custom_frequency:
                sub["frequency"] = ov.custom_frequency
            if ov.custom_amount is not None or ov.custom_frequency:
                factor = _FREQ_PER_MONTH.get(sub["frequency"], 1.0)
                sub["monthly_cost"] = round(sub["average_amount"] * factor, 2)
                sub["annual_cost"] = round(sub["monthly_cost"] * 12, 2)
            if ov.custom_next_date is not None:
                sub["next_expected_date"] = ov.custom_next_date.isoformat()
            sub["user_edited"] = True
        visible.append(sub)
    subs = sorted(visible, key=lambda x: -x["monthly_cost"])
    return {"subscriptions": subs, "count": len(subs),
            "confirmed_count": sum(1 for x in subs if x["status"] == "confirmed"),
            "potential_count": sum(1 for x in subs if x["status"] == "potential"),
            "total_monthly_cost": round(sum(x["monthly_cost"] for x in subs), 2),
            "total_annual_cost": round(sum(x["annual_cost"] for x in subs), 2),
            "currency": cur, "version": ADVANCED_VERSION,
            "note": "Detected subscriptions are potential until you confirm them; amounts come from your charge history."}


_FREQ_PER_MONTH = {"weekly": 30.0 / 7.0, "biweekly": 30.0 / 14.0, "monthly": 1.0,
                   "quarterly": 1.0 / 3.0, "yearly": 1.0 / 12.0}

import re as _re

def merchant_key(name) -> str:
    """Normalised merchant identity: lowercased, punctuation removed and
    common billing suffixes stripped, so 'Netflix', 'NETFLIX.COM' and
    'Netflix Pvt Ltd' share one key."""
    k = _re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    k = _re.sub(r"\b(com|in|inc|ltd|llc|pvt|private|limited|india|app|pay|subscription|subs)\b", " ", k)
    return _re.sub(r"\s+", "", k) or "unknown"


def set_subscription_override(db: Session, user_id: int, merchant: str, status: str,
                              custom_amount=None, custom_frequency=None, custom_next_date=None):
    if status not in ("confirmed", "dismissed"):
        raise ValueError("status must be 'confirmed' or 'dismissed'")
    key = merchant_key(merchant)
    row = db.query(SubscriptionOverride).filter(
        SubscriptionOverride.user_id == user_id,
        SubscriptionOverride.merchant_key == key).first()
    if row is None:
        row = SubscriptionOverride(user_id=user_id, merchant_key=key)
        db.add(row)
    row.merchant = merchant
    row.status = status
    if custom_amount is not None:
        row.custom_amount = custom_amount
    if custom_frequency is not None:
        row.custom_frequency = custom_frequency
    if custom_next_date is not None:
        row.custom_next_date = custom_next_date
    db.commit()
    db.refresh(row)
    return {"merchant": row.merchant, "merchant_key": row.merchant_key, "status": row.status,
            "custom_amount": float(row.custom_amount) if row.custom_amount is not None else None,
            "custom_frequency": row.custom_frequency,
            "custom_next_date": row.custom_next_date.isoformat() if row.custom_next_date else None}


def remove_subscription_override(db: Session, user_id: int, key: str) -> bool:
    row = db.query(SubscriptionOverride).filter(
        SubscriptionOverride.user_id == user_id,
        SubscriptionOverride.merchant_key == key).first()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ------------------------------------------------------------ budget forecast
def budget_forecast(db: Session, user_id: int):
    """Project each current-month budget to month-end using the daily
    run-rate so far. Deterministic; labelled as a projection."""
    cur = primary_currency(db, user_id)
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    elapsed = today.day
    remaining = days_in_month - elapsed
    budgets = db.query(Budget).filter(Budget.user_id == user_id, Budget.month == today.month, Budget.year == today.year).all()
    out = []
    for b in budgets:
        spent = float(_budget_spent_sql(db, user_id, cur, b, today.year, today.month))
        limit = float(b.amount)
        run_rate = spent / elapsed if elapsed else 0.0
        projected = spent + run_rate * remaining
        proj_util = (projected / limit * 100) if limit else 0.0
        if spent >= limit:
            risk = "exceeded"
        elif proj_util > 100:
            risk = "high"
        elif proj_util > 80:
            risk = "medium"
        else:
            risk = "low"
        out.append({
            "budget_id": b.id, "category_name": b.category_name, "limit_amount": limit,
            "spent": round(spent, 2), "remaining_budget": round(limit - spent, 2),
            "days_elapsed": elapsed, "days_remaining": remaining,
            "daily_run_rate": round(run_rate, 2),
            "projected_month_end_spend": round(projected, 2),
            "projected_utilisation_percent": round(proj_util, 2),
            "safe_daily_allowance": round(max(0.0, (limit - spent) / remaining), 2) if remaining else 0.0,
            "risk": risk,
        })
    out.sort(key=lambda x: -x["projected_utilisation_percent"])
    return {"month": today.month, "year": today.year, "budgets": out,
            "high_risk_count": sum(1 for x in out if x["risk"] in ("high", "exceeded")),
            "currency": cur, "version": ADVANCED_VERSION, "method": "daily_run_rate_projection"}


# ---------------------------------------------------------- cashflow forecast
def cashflow_projection(db: Session, user_id: int, horizon_days: int = 30):
    """Project income (trailing-90-day average rate) and expenses (ML
    forecast) over the horizon; net = income - expense. Honest flags."""
    cur = primary_currency(db, user_id)
    today = date.today()
    window_start = today - timedelta(days=90)
    income_90 = float(_dec(db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, Transaction.type == "income",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= window_start).scalar() or 0))
    days_covered = 90
    projected_income = round(income_90 / days_covered * horizon_days, 2) if income_90 > 0 else None

    from app.ml.forecasting.model import forecast as ml_forecast
    f = ml_forecast(db, user_id, horizon_days=horizon_days)
    projected_expense = f.get("predicted_amount")
    result = {
        "horizon_days": horizon_days, "currency": cur, "version": ADVANCED_VERSION,
        "projected_income": projected_income,
        "income_method": "trailing_90_day_average" if projected_income is not None else None,
        "projected_expense": projected_expense,
        "expense_method": f.get("method"),
        "forecast_insufficient_data": bool(f.get("insufficient_data")),
        "expense_prediction_interval": f.get("prediction_interval"),
    }
    if projected_income is not None and projected_expense is not None:
        result["projected_net"] = round(projected_income - projected_expense, 2)
        result["projected_savings_rate"] = round((projected_income - projected_expense) / projected_income * 100, 2) if projected_income else None
    else:
        result["projected_net"] = None
        result["projected_savings_rate"] = None
        result["note"] = "Projection needs both income history (90 days) and enough expense history for a forecast; nothing was fabricated."
    return result


# ------------------------------------------------------- cash-flow timeline
_FREQ_STEP_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 91, "yearly": 365}


def _income_pattern(db: Session, user_id: int, cur: str):
    """Dominant roughly-monthly income pattern (e.g. salary): the income
    merchant with >=2 charges and a 20-40 day median interval. Callers must
    label anything derived from this as ASSUMED — a detected pattern is
    evidence, not a confirmed payroll."""
    rows = db.query(Transaction.merchant, Transaction.amount, Transaction.date).filter(
        Transaction.user_id == user_id, Transaction.type == "income",
        func.coalesce(Transaction.currency, "INR") == cur).all()
    by_merchant = defaultdict(list)
    for merchant, amount, d in rows:
        by_merchant[(merchant or "").strip()].append((d, float(_dec(amount))))
    best = None
    for merchant, items in by_merchant.items():
        if len(items) < 2:
            continue
        items.sort()
        gaps = [(items[i + 1][0] - items[i][0]).days for i in range(len(items) - 1)]
        med_gap = statistics.median(gaps)
        if not (20 <= med_gap <= 40):
            continue
        med_amt = statistics.median([a for _, a in items])
        if med_amt <= 0:
            continue
        cand = {"merchant": merchant or "Income", "amount": round(med_amt, 2),
                "median_interval_days": int(med_gap),
                "typical_day_of_month": int(statistics.median([d.day for d, _ in items])),
                "last_date": items[-1][0], "occurrences": len(items)}
        if best is None or cand["occurrences"] > best["occurrences"]:
            best = cand
    return best


def _roll_forward(start: date, step_days: int, today: date, end: date):
    """All occurrences of a repeating date inside [today, end)."""
    if step_days <= 0:
        return []
    d = start
    guard = 0
    while d < today and guard < 400:
        d += timedelta(days=step_days)
        guard += 1
    out = []
    while d < end and guard < 800:
        out.append(d)
        d += timedelta(days=step_days)
        guard += 1
    return out


def cashflow_timeline(db: Session, user_id: int, horizon_days: int = 30):
    """Stage 3 (Feature C): a DATED cash-flow timeline, not just totals.

    Composition (all labelled):
    - income events from the detected monthly income pattern (ASSUMED) or
      user-defined recurring income (CONFIRMED);
    - obligation events from detected subscriptions, dashboard recurring
      groups and user-defined recurring expenses (pattern vs confirmed);
    - a baseline daily discretionary spend = trailing-90d expense minus
      the obligations' 90-day run-rate, so obligations are not counted
      twice.
    Balances are RELATIVE to today (starting balance 0): FinSight does not
    know the user's bank balance, so a 'shortage' means projected outflows
    exceed projected inflows within the horizon from a zero buffer —
    stated openly in `assumptions`."""
    if horizon_days not in (30, 60, 90):
        raise ValueError("horizon_days must be 30, 60 or 90")
    cur = primary_currency(db, user_id)
    summary = compute_summary(db, user_id)
    today = date.today()
    end = today + timedelta(days=horizon_days)
    if summary["transaction_count"] == 0:
        return {"horizon_days": horizon_days, "currency": cur, "insufficient_data": True,
                "message": "Add transactions to build a cash-flow timeline.",
                "events": [], "daily": [], "assumptions": [], "version": ADVANCED_VERSION}

    events = []  # {date, kind: income|obligation, label, amount, certainty}

    # --- obligations: detected subscriptions (pattern) ---
    subs = detect_subscriptions(db, user_id)
    sub_merchants = set()
    obligations_monthly = 0.0
    for sub in subs["subscriptions"]:
        sub_merchants.add((sub["merchant"] or "").strip().lower())
        obligations_monthly += float(sub["monthly_cost"])
        if not sub.get("next_expected_date"):
            continue
        step = _FREQ_STEP_DAYS.get(sub["frequency"], 30)
        for d in _roll_forward(date.fromisoformat(sub["next_expected_date"]), step, today, end):
            events.append({"date": d.isoformat(), "kind": "obligation",
                           "label": f"{sub['merchant']} (detected subscription)",
                           "amount": round(float(sub["average_amount"]), 2), "certainty": "pattern"})

    # --- obligations: recurring groups (is_recurring-flagged, cadence from
    # their real charge dates — the same groups the dashboard lists) ---
    rec_rows = db.query(Transaction.merchant, Transaction.category_name, Transaction.amount, Transaction.date).filter(
        Transaction.user_id == user_id, Transaction.is_recurring.is_(True),
        Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur).all()
    rec_groups = defaultdict(list)
    for merchant, cat, amount, d in rec_rows:
        rec_groups[((merchant or "").strip(), cat or "Uncategorized")].append((d, float(_dec(amount))))
    for (merchant, cat), items in rec_groups.items():
        if merchant.lower() in sub_merchants or len(items) < 2:
            continue
        items.sort()
        gaps = [(items[i + 1][0] - items[i][0]).days for i in range(len(items) - 1)]
        med_gap = int(statistics.median(gaps)) if gaps else 0
        if not (5 <= med_gap <= 40):
            continue
        avg_amt = round(statistics.median([a for _, a in items]), 2)
        obligations_monthly += avg_amt * 30.0 / med_gap
        for d in _roll_forward(items[-1][0] + timedelta(days=med_gap), med_gap, today, end):
            events.append({"date": d.isoformat(), "kind": "obligation",
                           "label": f"{merchant or cat} (recurring)",
                           "amount": avg_amt, "certainty": "pattern"})

    # --- user-defined recurring transactions (confirmed) ---
    confirmed_income_merchants = set()
    for r in db.query(RecurringTransaction).filter(
            RecurringTransaction.user_id == user_id, RecurringTransaction.active.is_(True)).all():
        if r.next_date is None:
            continue
        step = _FREQ_STEP_DAYS.get(r.frequency or "monthly", 30)
        amt = round(float(_dec(r.amount)), 2)
        if r.type == "income":
            confirmed_income_merchants.add((r.merchant or "").strip().lower())
            for d in _roll_forward(r.next_date, step, today, end):
                events.append({"date": d.isoformat(), "kind": "income",
                               "label": f"{r.merchant or r.description or 'Recurring income'} (scheduled)",
                               "amount": amt, "certainty": "confirmed"})
        else:
            obligations_monthly += amt * 30.0 / step
            for d in _roll_forward(r.next_date, step, today, end):
                events.append({"date": d.isoformat(), "kind": "obligation",
                               "label": f"{r.merchant or r.description or 'Recurring expense'} (scheduled)",
                               "amount": amt, "certainty": "confirmed"})

    # --- income: detected salary pattern (assumed) ---
    pattern = _income_pattern(db, user_id, cur)
    income_in_horizon = sum(e["amount"] for e in events if e["kind"] == "income")
    if pattern and pattern["merchant"].strip().lower() not in confirmed_income_merchants:
        step = pattern["median_interval_days"]
        for d in _roll_forward(pattern["last_date"] + timedelta(days=step), step, today, end):
            events.append({"date": d.isoformat(), "kind": "income",
                           "label": f"{pattern['merchant']} income (detected pattern)",
                           "amount": pattern["amount"], "certainty": "assumed"})
            income_in_horizon += pattern["amount"]
    if income_in_horizon == 0:
        monthly_inc = _monthly_from_daily(daily_totals(db, user_id, cur, "income"))
        if monthly_inc:
            avg_income = round(float(sum(monthly_inc.values()) / len(monthly_inc)), 2)
            d = date(today.year, today.month, 1)
            while d < end:
                if d >= today:
                    events.append({"date": d.isoformat(), "kind": "income",
                                   "label": "Average monthly income (assumed)",
                                   "amount": avg_income, "certainty": "assumed"})
                d = date(d.year + (1 if d.month == 12 else 0), 1 if d.month == 12 else d.month + 1, 1)

    # --- baseline daily discretionary spend (obligations removed) ---
    window_start = today - timedelta(days=90)
    expense_90 = float(_dec(db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= window_start).scalar() or 0))
    refunds_90 = float(_dec(db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, Transaction.type == "refund",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= window_start).scalar() or 0))
    obligations_90 = obligations_monthly * 3.0
    baseline_daily = max(0.0, (expense_90 - refunds_90 - obligations_90) / 90.0)

    # --- daily walk (relative balance, starts at 0 today) ---
    by_date = defaultdict(lambda: {"income": 0.0, "obligations": 0.0})
    for e in events:
        by_date[e["date"]]["income" if e["kind"] == "income" else "obligations"] += e["amount"]
    daily, balance = [], 0.0
    lowest = {"date": today.isoformat(), "balance": 0.0}
    first_shortage = None
    eom_balance = None
    month_end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    for i in range(horizon_days):
        d = today + timedelta(days=i)
        day = by_date[d.isoformat()]
        balance += day["income"] - day["obligations"] - baseline_daily
        balance_r = round(balance, 2)
        daily.append({"date": d.isoformat(), "balance": balance_r,
                      "income": round(day["income"], 2), "obligations": round(day["obligations"], 2),
                      "baseline_expense": round(baseline_daily, 2)})
        if balance_r < lowest["balance"]:
            lowest = {"date": d.isoformat(), "balance": balance_r}
        if first_shortage is None and balance_r < 0:
            first_shortage = d.isoformat()  # provisional; refined below
        if d == month_end:
            eom_balance = balance_r
    # Refine the shortage flag: between income events the balance can only
    # fall, so a one-day dip that the next income event itself repairs is a
    # payday-timing artifact, not a shortage. A shortage starts on the
    # first negative day whose balance is NOT restored to >= 0 by the next
    # income event (inclusive) or by the horizon end.
    if first_shortage is not None:
        income_dates = sorted({e["date"] for e in events if e["kind"] == "income"})
        refined = None
        for idx, row in enumerate(daily):
            if row["balance"] >= 0:
                continue
            nxt = next((x for x in income_dates if x > row["date"]), None)
            recovered = False
            for later in daily[idx + 1:]:
                if nxt is not None and later["date"] > nxt:
                    break
                if later["balance"] >= 0:
                    recovered = True
                    break
            if not recovered:
                refined = row["date"]
                break
        first_shortage = refined
    obligations_total = round(sum(e["amount"] for e in events if e["kind"] == "obligation"), 2)
    income_total = round(sum(e["amount"] for e in events if e["kind"] == "income"), 2)
    return {
        "horizon_days": horizon_days, "currency": cur, "insufficient_data": False,
        "starting_balance": None, "balance_basis": "relative_to_today",
        "events": sorted(events, key=lambda e: e["date"]), "daily": daily,
        "lowest_projected_balance": lowest, "first_shortage_date": first_shortage,
        "end_of_month_balance": eom_balance,
        "totals": {"projected_income": income_total, "projected_obligations": obligations_total,
                   "projected_baseline_expenses": round(baseline_daily * horizon_days, 2),
                   "projected_net": round(income_total - obligations_total - baseline_daily * horizon_days, 2),
                   "obligations_monthly_run_rate": round(obligations_monthly, 2)},
        "assumptions": [
            "Balances are relative to today (starting balance 0) — FinSight does not know your bank balance.",
            "Detected income is labelled 'assumed': a pattern in past deposits, not a guaranteed payroll.",
            "Detected subscriptions and recurring charges are labelled 'pattern', not confirmed bills.",
            "A shortage is flagged only when the projected balance goes negative and is not restored by the next projected income — an overnight dip before payday is not counted.",
            f"Everyday spending is a flat baseline of {round(baseline_daily, 2)} per day (trailing 90 days, obligations removed to avoid double counting).",
        ],
        "version": ADVANCED_VERSION,
    }


# -------------------------------------------------------------- affordability
def affordability(db: Session, user_id: int, item_name: str, cost, months: int):
    """Can the user afford `cost` within `months`, given their average monthly
    surplus over the last 3 calendar months (deterministic)?"""
    cur = primary_currency(db, user_id)
    cost_f = float(cost)
    today = date.today()
    keys = []
    y, m = today.year, today.month
    for _ in range(3):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        keys.append((y, m))
    # Stage 2: one grouped SQL query for the whole 3-month window.
    win_start = date(keys[-1][0], keys[-1][1], 1)
    win_end = date(today.year, today.month, 1)
    sums = {t: float(_dec(v or 0)) for t, v in db.query(Transaction.type, func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= win_start, Transaction.date < win_end).group_by(Transaction.type).all()}
    inc, exp, ref = sums.get("income", 0.0), sums.get("expense", 0.0), sums.get("refund", 0.0)
    present = {(d.year, d.month) for (d,) in db.query(Transaction.date).filter(
        Transaction.user_id == user_id, func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= win_start, Transaction.date < win_end).distinct().all()}
    months_with_data = len([k for k in keys if k in present]) or 1
    surplus = (inc - max(0.0, exp - ref)) / months_with_data
    required = cost_f / months
    feasible = surplus >= required and surplus > 0
    if surplus > 0:
        import math
        months_needed = math.ceil(cost_f / surplus)
        y2, m2 = today.year, today.month + months_needed
        while m2 > 12:
            y2, m2 = y2 + 1, m2 - 12
        target = date(y2, m2, min(today.day, calendar.monthrange(y2, m2)[1])).isoformat()
    else:
        months_needed, target = None, None
    return {
        "item_name": item_name, "cost": round(cost_f, 2), "requested_months": months,
        "average_monthly_surplus": round(surplus, 2),
        "required_monthly_saving": round(required, 2),
        "feasible_within_requested_months": feasible,
        "shortfall_per_month": round(max(0.0, required - surplus), 2),
        "months_needed_at_current_surplus": months_needed,
        "projected_affordable_date": target,
        "based_on": "average income minus expenses over the last 3 calendar months",
        "currency": cur, "version": ADVANCED_VERSION,
    }


# ------------------------------------------------------------- smart insights
def smart_insights(db: Session, user_id: int):
    """Rule-based insights computed from the user's real data. Every insight
    carries the numbers behind it; the LLM may phrase them, never invent them."""
    cur = primary_currency(db, user_id)
    summary = compute_summary(db, user_id)
    insights = []
    if summary["transaction_count"] == 0:
        return {"insights": [], "count": 0, "insufficient_data": True,
                "message": "Add transactions to generate insights.", "currency": cur, "version": ADVANCED_VERSION}

    today = date.today()
    cur_key, prev_key = _month_key(today), _month_key(date(today.year, today.month, 1) - timedelta(days=1))

    # Stage 2: category-by-day sums from one grouped SQL query, rolled up
    # to months in Python (rows = categories x days, not transactions).
    _cat_rows = db.query(Transaction.category_name, Transaction.date, Transaction.type,
                         func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, Transaction.type.in_(("expense", "refund")),
        func.coalesce(Transaction.currency, "INR") == cur
    ).group_by(Transaction.category_name, Transaction.date, Transaction.type).all()
    _by_month = defaultdict(lambda: defaultdict(lambda: D0))
    for _cat, _d, _t, _total in _cat_rows:
        _by_month[_month_key(_d)][_cat or "Uncategorized"] += (_dec(_total or 0) if _t == "expense" else -_dec(_total or 0))

    def cat_month(key):
        return _by_month.get(key, {})

    cur_cats, prev_cats = cat_month(cur_key), cat_month(prev_key)
    for cat, val in cur_cats.items():
        prev = prev_cats.get(cat, D0)
        if prev > 0 and val > prev:
            pct = float((val - prev) / prev * 100)
            if pct >= 20 and float(val - prev) >= 500:
                insights.append({"type": "category_spike", "severity": "warning",
                                 "title": f"{cat} spending is up {pct:.0f}% this month",
                                 "detail": f"{cat}: ₹{float(prev):,.2f} last month → ₹{float(val):,.2f} so far this month.",
                                 "metric": {"category": cat, "change_percent": round(pct, 1)}})

    cats = category_breakdown(db, user_id)
    total_exp = float(summary["total_expense"])
    if cats and total_exp > 0:
        top = cats[0]
        share = top["total"] / total_exp * 100
        if share >= 30:
            insights.append({"type": "concentration", "severity": "info",
                             "title": f"{top['category']} is {share:.0f}% of all spending",
                             "detail": f"Your largest category is {top['category']} at ₹{top['total']:,.2f} of ₹{total_exp:,.2f} total expenses.",
                             "metric": {"category": top["category"], "share_percent": round(share, 1)}})

    rate = float(summary["savings_rate"])
    if rate < 0:
        insights.append({"type": "negative_savings", "severity": "warning",
                         "title": "You are spending more than you earn",
                         "detail": f"Savings rate is {rate:.2f}% (net ₹{float(summary['net_balance']):,.2f}). The simulator can show what a small category cut would change.",
                         "metric": {"savings_rate": rate}})
    elif rate >= 20:
        insights.append({"type": "strong_savings", "severity": "positive",
                         "title": "Savings rate at a healthy level",
                         "detail": f"Savings rate is {rate:.2f}%, at or above the commonly used 20% benchmark.",
                         "metric": {"savings_rate": rate}})

    subs = detect_subscriptions(db, user_id)
    if subs["count"]:
        monthly_income_avg = float(summary["total_income"]) / max(1, len(_monthly_from_daily(daily_totals(db, user_id, cur, "income"))))
        share = (subs["total_monthly_cost"] / monthly_income_avg * 100) if monthly_income_avg else 0.0
        insights.append({"type": "subscriptions", "severity": "warning" if share >= 10 else "info",
                         "title": f"{subs['count']} subscriptions cost ₹{subs['total_monthly_cost']:,.2f}/month",
                         "detail": f"Detected recurring charges total ₹{subs['total_annual_cost']:,.2f} per year ({share:.1f}% of average monthly income).",
                         "metric": {"count": subs["count"], "monthly_cost": subs["total_monthly_cost"]}})
        for s in subs["subscriptions"]:
            if s["price_change_percent"] > 2:
                insights.append({"type": "price_hike", "severity": "warning",
                                 "title": f"{s['merchant']} raised its price by {s['price_change_percent']:.0f}%",
                                 "detail": f"{s['merchant']} now charges ₹{s['average_amount']:,.2f} per {s['frequency']} cycle.",
                                 "metric": {"merchant": s["merchant"], "change_percent": s["price_change_percent"]}})

    bf = budget_forecast(db, user_id)
    for b in bf["budgets"]:
        if b["risk"] in ("high", "exceeded"):
            insights.append({"type": "budget_risk", "severity": "warning",
                             "title": f"{b['category_name']} budget at risk ({b['risk']})",
                             "detail": f"Spent ₹{b['spent']:,.2f} of ₹{b['limit_amount']:,.2f}; at the current run-rate the month ends near ₹{b['projected_month_end_spend']:,.2f}. Safe daily allowance: ₹{b['safe_daily_allowance']:,.2f}.",
                             "metric": {"category": b["category_name"], "projected_utilisation_percent": b["projected_utilisation_percent"]}})

    big_row = db.query(Transaction).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= today - timedelta(days=30)).order_by(Transaction.amount.desc()).first()
    if big_row is not None:
        _amounts = [float(a) for (a,) in db.query(Transaction.amount).filter(
            Transaction.user_id == user_id, Transaction.type == "expense",
            func.coalesce(Transaction.currency, "INR") == cur).all()]
        med = statistics.median(_amounts) if _amounts else 0.0
        if med > 0 and float(big_row.amount) >= 5 * med:
            insights.append({"type": "large_purchase", "severity": "info",
                             "title": "A recent purchase stands out",
                             "detail": f"₹{float(big_row.amount):,.2f} at {big_row.merchant or 'unknown merchant'} on {big_row.date.isoformat()} is about {float(big_row.amount)/med:.0f}x your median expense (₹{med:,.2f}).",
                             "metric": {"amount": float(big_row.amount), "median_expense": round(med, 2)}})

    refunds_total = float(summary.get("refund_total", 0))
    if refunds_total > 0:
        insights.append({"type": "refunds", "severity": "positive",
                         "title": f"₹{refunds_total:,.2f} recovered in refunds",
                         "detail": "Refunds already offset your category spending in all FinSight totals.",
                         "metric": {"refund_total": refunds_total}})

    # ---- Stage 6 (Feature E): behaviour intelligence ----
    from sqlalchemy import case as _case
    _today = date.today()
    _d1 = timedelta(days=1)

    def _exp_sum(start, end, exclude_cats=None, recurring_only=False):
        q = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == user_id, Transaction.type == "expense",
            func.coalesce(Transaction.currency, "INR") == cur,
            Transaction.date >= start, Transaction.date < end)
        if exclude_cats:
            q = q.filter(~Transaction.category_name.in_(exclude_cats))
        if recurring_only:
            q = q.filter(Transaction.is_recurring.is_(True))
        return float(q.scalar() or 0)

    _ESSENTIAL = ["Rent", "Utilities", "Groceries", "Transport", "Healthcare",
                  "Education", "Insurance", "Loan", "EMI", "Taxes"]
    _recent_disc = _exp_sum(_today - timedelta(days=90), _today + _d1, _ESSENTIAL)
    _prior_disc = _exp_sum(_today - timedelta(days=180), _today - timedelta(days=90), _ESSENTIAL)
    if _prior_disc >= 1000 and _recent_disc > _prior_disc * 1.15 and (_recent_disc - _prior_disc) > 2000:
        _pct = (_recent_disc - _prior_disc) / _prior_disc * 100
        insights.append({"type": "lifestyle_inflation", "severity": "warning",
                         "title": f"Discretionary spending is inflating ({_pct:.0f}% up)",
                         "detail": f"Non-essential spending was ₹{_prior_disc:,.2f} in the earlier 90 days and ₹{_recent_disc:,.2f} in the last 90 days.",
                         "evidence": f"90-day discretionary totals compared like-for-like (essentials such as rent, groceries and utilities excluded): ₹{_prior_disc:,.0f} → ₹{_recent_disc:,.0f}.",
                         "suggested_action": "Pick the fastest-growing discretionary category in Analytics and set a budget for it.",
                         "metric": {"recent_90d": round(_recent_disc, 2), "prior_90d": round(_prior_disc, 2), "change_percent": round(_pct, 1)}})

    _micro = db.query(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.amount < 200, Transaction.date >= _today - timedelta(days=30),
        Transaction.date < _today + _d1).first()
    if _micro and _micro[0] >= 25:
        insights.append({"type": "micro_transaction_cluster", "severity": "info",
                         "title": f"{_micro[0]} small purchases in 30 days add up",
                         "detail": f"Expenses under ₹200 total ₹{float(_micro[1]):,.2f} in the last 30 days — individually small, collectively a real line item.",
                         "evidence": f"{_micro[0]} transactions below ₹200 in the last 30 days sum to ₹{float(_micro[1]):,.2f}.",
                         "suggested_action": "Review the smallest recurring merchants — one cancelled habit often covers a subscription.",
                         "metric": {"count_30d": int(_micro[0]), "total_30d": round(float(_micro[1]), 2)}})

    if db.bind is not None and db.bind.dialect.name == "sqlite":
        _dow = func.strftime("%w", Transaction.date)
        _is_weekend = _dow.in_(["0", "6"])
    else:
        _is_weekend = func.extract("dow", Transaction.date).in_([0, 6])
    _wk = db.query(
        func.coalesce(func.sum(_case((_is_weekend, Transaction.amount), else_=0)), 0),
        func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= _today - timedelta(days=90), Transaction.date < _today + _d1).first()
    if _wk and float(_wk[1]) >= 5000:
        _share = float(_wk[0]) / float(_wk[1]) * 100
        if _share > 40:
            insights.append({"type": "weekend_spending", "severity": "info",
                             "title": f"{_share:.0f}% of spending lands on weekends",
                             "detail": f"₹{float(_wk[0]):,.2f} of ₹{float(_wk[1]):,.2f} spent in the last 90 days fell on a Saturday or Sunday (2 of 7 days would be ~29%).",
                             "evidence": f"Weekend share of 90-day expenses: {_share:.1f}%.",
                             "suggested_action": "A weekend spending cap in Budgets is the usual fix if this is unintentional.",
                             "metric": {"weekend_share_percent": round(_share, 1)}})

    _rec_recent = _exp_sum(_today - timedelta(days=90), _today + _d1, recurring_only=True)
    _rec_prior = _exp_sum(_today - timedelta(days=180), _today - timedelta(days=90), recurring_only=True)
    if _rec_prior >= 500 and _rec_recent > _rec_prior * 1.2 and (_rec_recent - _rec_prior) > 500:
        _pct = (_rec_recent - _rec_prior) / _rec_prior * 100
        insights.append({"type": "recurring_creep", "severity": "warning",
                         "title": f"Recurring charges crept up {_pct:.0f}%",
                         "detail": f"Charges flagged recurring rose from ₹{_rec_prior:,.2f} (earlier 90 days) to ₹{_rec_recent:,.2f} (last 90 days).",
                         "evidence": f"Recurring-flagged expense totals: ₹{_rec_prior:,.0f} → ₹{_rec_recent:,.0f} across consecutive 90-day windows.",
                         "suggested_action": "Open the subscriptions panel and dismiss or cancel anything you no longer use.",
                         "metric": {"recent_90d": round(_rec_recent, 2), "prior_90d": round(_rec_prior, 2), "change_percent": round(_pct, 1)}})

    rank = {"warning": 0, "info": 1, "positive": 2}
    insights.sort(key=lambda i: rank.get(i["severity"], 1))
    return {"insights": insights[:10], "count": min(len(insights), 10), "total_generated": len(insights),
            "insufficient_data": False, "currency": cur, "version": ADVANCED_VERSION,
            "source": "deterministic_rules_over_user_transactions"}


# ------------------------------------------------------- Stage 8: goals v2
def _average_monthly_net(db: Session, user_id: int, cur: str, months: int = 6):
    """Average monthly (income - expense) over the trailing `months`
    calendar months, counting only months that have income. Returns
    (avg_net, months_with_income). Transfers excluded, refunds offset."""
    today = date.today()
    start = date(today.year, today.month, 1)
    for _ in range(months - 1):
        start = date(start.year - (1 if start.month == 1 else 0),
                     12 if start.month == 1 else start.month - 1, 1)
    rows = db.query(
        func.strftime("%Y-%m", Transaction.date) if db.bind.dialect.name == "sqlite"
        else func.to_char(Transaction.date, "YYYY-MM"),
        Transaction.type, func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user_id,
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= start, Transaction.type.in_(("income", "expense", "refund"))).group_by(
        func.strftime("%Y-%m", Transaction.date) if db.bind.dialect.name == "sqlite"
        else func.to_char(Transaction.date, "YYYY-MM"), Transaction.type).all()
    by_month = {}
    for mk, type_, total in rows:
        d = by_month.setdefault(mk, {"income": 0.0, "expense": 0.0})
        if type_ == "income":
            d["income"] += float(total)
        else:
            d["expense"] += float(total) * (1 if type_ == "expense" else -1)
    nets = [v["income"] - v["expense"] for v in by_month.values() if v["income"] > 0]
    if not nets:
        return None, 0
    return round(sum(nets) / len(nets), 2), len(nets)


def goal_forecast(db: Session, user_id: int, goal) -> dict:
    """Stage 8 (Goals v2): when will this goal be reached at the user's
    recent average monthly surplus, and what monthly contribution would
    the deadline require? All arithmetic is deterministic; when there is
    no positive surplus the forecast says so instead of inventing a date."""
    import math
    cur = primary_currency(db, user_id)
    target = float(goal.target_amount)
    current = float(goal.current_amount or 0)
    remaining = max(0.0, target - current)
    out = {"goal_id": goal.id, "name": goal.name, "target_amount": target,
           "current_amount": current, "remaining": round(remaining, 2),
           "progress_percent": round(current / target * 100, 1) if target else 0.0,
           "deadline": goal.deadline.isoformat() if goal.deadline else None,
           "currency": cur, "version": ADVANCED_VERSION}
    if remaining <= 0:
        out.update({"status": "achieved", "months_at_current_pace": 0,
                    "projected_completion_date": date.today().isoformat()})
        return out
    avg_net, months_seen = _average_monthly_net(db, user_id, cur)
    out["average_monthly_surplus"] = avg_net
    out["surplus_basis_months"] = months_seen
    if goal.deadline:
        months_left = (goal.deadline.year - date.today().year) * 12 + (goal.deadline.month - date.today().month) + 1
        out["months_until_deadline"] = months_left
        out["required_monthly_contribution"] = round(remaining / months_left, 2) if months_left > 0 else None
    else:
        out["months_until_deadline"] = None
        out["required_monthly_contribution"] = None
    if avg_net is None or avg_net <= 0:
        out.update({"status": "cannot_project",
                    "message": "Your recent months show no positive average surplus, so a completion date cannot be projected honestly. The required monthly contribution for the deadline is shown when a deadline is set.",
                    "months_at_current_pace": None, "projected_completion_date": None})
        return out
    months_needed = math.ceil(remaining / avg_net)
    y = date.today().year + (date.today().month - 1 + months_needed) // 12
    m = (date.today().month - 1 + months_needed) % 12 + 1
    projected = date(y, m, 1)
    out.update({"status": "on_track" if (goal.deadline is None or projected <= goal.deadline) else "behind",
                "months_at_current_pace": months_needed,
                "projected_completion_date": projected.isoformat(),
                "message": f"At your recent average surplus of ₹{avg_net:,.2f}/month (over {months_seen} month(s) with income), the remaining ₹{remaining:,.2f} takes about {months_needed} month(s)."})
    return out


# -------------------------------------------------- Stage 8: simulator v2
def scenario_trajectory(db: Session, user_id: int, *, category_name=None, reduction_percent=0.0,
                        extra_monthly_savings=0.0, income_change_percent=0.0,
                        one_off_expense=0.0, months=12) -> dict:
    """Stage 8 (Simulator v2): month-by-month cumulative-balance trajectory
    for the baseline (recent average month) versus a scenario. Averages
    come from the trailing 6 months; every assumption is listed."""
    cur = primary_currency(db, user_id)
    today = date.today()
    start = date(today.year, today.month, 1)
    for _ in range(5):
        start = date(start.year - (1 if start.month == 1 else 0),
                     12 if start.month == 1 else start.month - 1, 1)
    agg = db.query(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user_id, func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= start, Transaction.type.in_(("income", "expense", "refund"))).group_by(Transaction.type).all()
    totals = {t: float(v) for t, v in agg}
    months_seen_q = db.query(func.count(func.distinct(
        func.strftime("%Y-%m", Transaction.date) if db.bind.dialect.name == "sqlite"
        else func.to_char(Transaction.date, "YYYY-MM")))).filter(
        Transaction.user_id == user_id, func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= start, Transaction.type == "income").scalar() or 0
    n_months = max(int(months_seen_q), 1)
    avg_income = totals.get("income", 0.0) / n_months
    avg_expense = (totals.get("expense", 0.0) - totals.get("refund", 0.0)) / n_months
    cat_monthly = 0.0
    if category_name:
        cat_total = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == user_id, func.coalesce(Transaction.currency, "INR") == cur,
            Transaction.date >= start, Transaction.type == "expense",
            func.lower(Transaction.category_name) == category_name.lower()).scalar() or 0
        cat_monthly = float(cat_total) / n_months
    reduction = min(max(float(reduction_percent or 0), 0.0), 100.0)
    cat_saving = cat_monthly * reduction / 100.0
    scen_income = avg_income * (1 + float(income_change_percent or 0) / 100.0)
    scen_expense = avg_expense - cat_saving - float(extra_monthly_savings or 0)
    base_net = avg_income - avg_expense
    scen_net = scen_income - scen_expense
    points, b_bal, s_bal = [], 0.0, 0.0
    for i in range(1, int(months) + 1):
        b_bal += base_net
        s_bal += scen_net - (float(one_off_expense or 0) if i == 1 else 0.0)
        y = today.year + (today.month - 1 + i) // 12
        m = (today.month - 1 + i) % 12 + 1
        points.append({"month_index": i, "month": f"{y:04d}-{m:02d}",
                       "baseline_balance": round(b_bal, 2), "scenario_balance": round(s_bal, 2)})
    return {"currency": cur, "months": int(months), "points": points,
            "baseline_monthly_net": round(base_net, 2), "scenario_monthly_net": round(scen_net, 2),
            "end_difference": round(s_bal - b_bal, 2),
            "assumptions": [
                f"Baseline uses trailing-6-month averages over {n_months} month(s) with income: income ₹{avg_income:,.2f}/mo, expenses ₹{avg_expense:,.2f}/mo.",
                f"Category reduction applies to '{category_name}' averaging ₹{cat_monthly:,.2f}/mo." if category_name else "No category reduction applied.",
                f"Extra monthly savings of ₹{float(extra_monthly_savings or 0):,.2f} treated as reduced spending.",
                f"Income change of {float(income_change_percent or 0):g}% applied to average income.",
                "Balances are cumulative net position relative to today, not a bank balance; inflation, interest and irregular bills are not modelled."],
            "version": ADVANCED_VERSION}


# ---------------------------------------------------- Stage 9: challenges
def weekly_challenges(db: Session, user_id: int) -> dict:
    """Stage 9: small, concrete weekly challenges computed from the user's
    own recent behaviour, each with live progress. Suggestions only —
    nothing is enforced and targets derive from the user's own baseline."""
    cur = primary_currency(db, user_id)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    last_monday = monday - timedelta(days=7)
    challenges = []

    def _cat_sum(cat, start, end):
        return float(db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.user_id == user_id, Transaction.type == "expense",
            func.coalesce(Transaction.currency, "INR") == cur,
            Transaction.category_name == cat,
            Transaction.date >= start, Transaction.date < end).scalar() or 0)

    # top discretionary category last week -> "spend 10% less this week"
    ESSENTIAL = ("Rent", "Utilities", "Groceries", "Transport", "Healthcare", "Education", "Insurance")
    top = db.query(Transaction.category_name, func.sum(Transaction.amount).label("t")).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur,
        Transaction.date >= last_monday, Transaction.date < monday,
        ~Transaction.category_name.in_(ESSENTIAL)).group_by(Transaction.category_name).order_by(func.sum(Transaction.amount).desc()).first()
    if top and float(top[1]) >= 500:
        last_week = float(top[1])
        target = round(last_week * 0.9, 2)
        spent = _cat_sum(top[0], monday, today + timedelta(days=1))
        challenges.append({"id": "cut_top_category", "title": f"Spend 10% less on {top[0]} this week",
                           "detail": f"You spent ₹{last_week:,.2f} on {top[0]} last week; the target is ₹{target:,.2f} this week.",
                           "target_amount": target, "progress_amount": round(spent, 2),
                           "progress_percent": round(min(100.0, spent / target * 100), 1) if target else 0.0,
                           "status": "exceeded" if spent > target else "in_progress"})
    # micro-spend pause: at most 5 sub-₹200 purchases this week
    micro = db.query(func.count(Transaction.id)).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur, Transaction.amount < 200,
        Transaction.date >= monday, Transaction.date < today + timedelta(days=1)).scalar() or 0
    challenges.append({"id": "micro_pause", "title": "Keep small purchases (under ₹200) to 5 or fewer this week",
                       "detail": "Small leaks add up — this challenge is based on your micro-transaction pattern.",
                       "target_amount": 5, "progress_amount": int(micro),
                       "progress_percent": round(min(100.0, int(micro) / 5 * 100), 1),
                       "status": "exceeded" if micro > 5 else "in_progress"})
    # savings nudge: beat last month's savings rate pace
    avg_net, months_seen = _average_monthly_net(db, user_id, cur)
    if avg_net and avg_net > 0:
        target = round(avg_net * 1.05 / 4, 2)  # weekly slice of +5% on the monthly surplus
        challenges.append({"id": "surplus_plus_5", "title": "Bank 5% more than your usual weekly surplus",
                           "detail": f"Your average monthly surplus is ₹{avg_net:,.2f}; a +5% weekly slice is ₹{target:,.2f}. Progress is assessed at week end from your net position.",
                           "target_amount": target, "progress_amount": None,
                           "progress_percent": None, "status": "in_progress"})
    return {"week_start": monday.isoformat(), "challenges": challenges,
            "currency": cur, "version": ADVANCED_VERSION,
            "note": "Challenges are computed from your own recent data and are purely advisory."}
