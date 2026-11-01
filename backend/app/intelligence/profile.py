"""
Personal Financial Digital Twin (Stage 3, Feature A).

A continuously computed profile of the user's finances, derived ONLY from
their structured transaction records via the Intelligence Engine — no
invented characteristics, no separate AI-generated database. Every figure
either matches an analytics endpoint exactly or is labelled as a gap when
history is insufficient. Users inspect this profile in the UI; pattern
correction arrives with subscription/category overrides (Stage 4).
"""
import statistics
from collections import defaultdict
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics.advanced import _income_pattern, _monthly_from_daily
from app.analytics.service import daily_totals, primary_currency, _dec, D0
from app.models.models import Transaction, Budget, FinancialGoal


def _monthly_net(db, user_id, cur):
    exp = _monthly_from_daily(daily_totals(db, user_id, cur, "expense"))
    ref = _monthly_from_daily(daily_totals(db, user_id, cur, "refund"))
    inc = _monthly_from_daily(daily_totals(db, user_id, cur, "income"))
    keys = sorted(set(exp) | set(inc))
    return keys, inc, {k: exp.get(k, D0) - ref.get(k, D0) for k in keys}


def build_profile(db: Session, user_id: int, engine) -> dict:
    cur = primary_currency(db, user_id)
    summary = engine.summary()
    gaps: list[str] = []

    if summary["transaction_count"] == 0:
        return {"currency": cur, "insufficient_data": True,
                "message": "Your financial profile is built from your transactions; add or import transactions to create it.",
                "data_gaps": ["No transactions recorded yet."]}

    keys, monthly_inc, monthly_net_exp = _monthly_net(db, user_id, cur)
    months_observed = len(keys)
    inc_values = [float(monthly_inc.get(k, D0)) for k in keys]
    exp_values = [float(monthly_net_exp.get(k, D0)) for k in keys]
    avg_income = sum(inc_values) / months_observed if months_observed else 0.0
    avg_expense = sum(exp_values) / months_observed if months_observed else 0.0

    # ---- income patterns ----
    sources_rows = db.query(Transaction.merchant, func.sum(Transaction.amount), func.count(Transaction.id)).filter(
        Transaction.user_id == user_id, Transaction.type == "income",
        func.coalesce(Transaction.currency, "INR") == cur).group_by(Transaction.merchant).all()
    total_income = float(summary["total_income"]) or 0.0
    sources = [{"merchant": (m or "Unknown"), "total": round(float(_dec(t or 0)), 2),
                "share_percent": round(float(_dec(t or 0)) / total_income * 100, 1) if total_income else 0.0,
                "payments": c} for m, t, c in sorted(sources_rows, key=lambda r: -float(_dec(r[1] or 0)))]
    pattern = _income_pattern(db, user_id, cur)
    if months_observed >= 2 and avg_income > 0:
        inc_cv = statistics.pstdev(inc_values) / avg_income if len(inc_values) > 1 else 0.0
    else:
        inc_cv = None
        gaps.append("Less than two months of income history — income regularity cannot be assessed yet.")
    income_patterns = {
        "average_monthly_income": round(avg_income, 2),
        "months_observed": months_observed,
        "regularity_cv": round(inc_cv, 3) if inc_cv is not None else None,
        "regularity_label": ("stable" if inc_cv is not None and inc_cv <= 0.15 else
                             "moderate" if inc_cv is not None and inc_cv <= 0.35 else
                             "variable" if inc_cv is not None else None),
        "primary_source": ({"merchant": pattern["merchant"], "typical_amount": pattern["amount"],
                            "typical_day_of_month": pattern["typical_day_of_month"],
                            "occurrences": pattern["occurrences"]} if pattern else None),
        "sources": sources,
    }
    if pattern is None:
        gaps.append("No dominant monthly income pattern detected — income timing is not predicted.")

    # ---- expense patterns ----
    cats = engine.category_breakdown()
    total_expense = float(summary["total_expense"]) or 0.0
    top_categories = [{"category": c["category"], "total": c["total"],
                       "monthly_average": round(c["total"] / months_observed, 2) if months_observed else c["total"],
                       "share_percent": round(c["total"] / total_expense * 100, 1) if total_expense else 0.0}
                      for c in cats[:5]]
    discretionary_names = {"Food & Dining", "Entertainment", "Shopping", "Travel"}
    discretionary_total = sum(c["total"] for c in cats if c["category"] in discretionary_names)
    expense_patterns = {
        "average_monthly_expense": round(avg_expense, 2),
        "top_categories": top_categories,
        "discretionary_share_percent": round(discretionary_total / total_expense * 100, 1) if total_expense else 0.0,
    }

    # ---- spending consistency ----
    if len(exp_values) >= 2 and avg_expense > 0:
        cv = statistics.pstdev(exp_values) / avg_expense
        consistency = {"monthly_cv": round(cv, 3),
                       "label": "stable" if cv <= 0.15 else "moderate" if cv <= 0.45 else "variable",
                       "months_observed": months_observed}
    else:
        cv = None
        consistency = {"monthly_cv": None, "label": None, "months_observed": months_observed}
        gaps.append("Less than two months of spending — spending consistency cannot be assessed yet.")

    # ---- recurring obligations ----
    subs = engine.subscriptions()
    obligations_monthly = float(subs["total_monthly_cost"])
    recurring_obligations = {
        "subscriptions_monthly_total": obligations_monthly,
        "subscriptions_count": subs["count"],
        "share_of_income_percent": round(obligations_monthly / avg_income * 100, 1) if avg_income else None,
    }

    # ---- savings behavior ----
    surplus_by_month = [float(monthly_inc.get(k, D0)) - float(monthly_net_exp.get(k, D0)) for k in keys]
    savings_behavior = {
        "overall_savings_rate_percent": float(summary["savings_rate"]),
        "average_monthly_surplus": round(sum(surplus_by_month) / months_observed, 2) if months_observed else 0.0,
        "positive_months": sum(1 for v in surplus_by_month if v > 0),
        "total_months": months_observed,
    }

    # ---- budget adherence (current month) ----
    today = date.today()
    budgets = db.query(Budget).filter(Budget.user_id == user_id, Budget.month == today.month, Budget.year == today.year).all()
    if budgets:
        from app.analytics.advanced import _budget_spent_sql
        utils = []
        for b in budgets:
            spent = _budget_spent_sql(db, user_id, cur, b, today.year, today.month)
            utils.append(float(spent) / float(b.amount) * 100 if b.amount else 0.0)
        budget_adherence = {"budgets_this_month": len(budgets),
                            "average_utilisation_percent": round(sum(utils) / len(utils), 1),
                            "over_budget_count": sum(1 for u in utils if u > 100)}
    else:
        budget_adherence = {"budgets_this_month": 0, "average_utilisation_percent": None, "over_budget_count": 0}
        gaps.append("No budgets set for this month — budget adherence is not assessed.")

    # ---- goals ----
    goals = db.query(FinancialGoal).filter(FinancialGoal.user_id == user_id).all()
    if goals:
        total_target = sum(float(g.target_amount or 0) for g in goals)
        total_saved = sum(float(g.current_amount or 0) for g in goals)
        goals_block = {"count": len(goals), "total_target": round(total_target, 2),
                       "total_saved": round(total_saved, 2),
                       "overall_progress_percent": round(total_saved / total_target * 100, 1) if total_target else 0.0,
                       "nearest_deadline": min((g.deadline.isoformat() for g in goals if g.deadline), default=None)}
    else:
        goals_block = {"count": 0, "total_target": 0.0, "total_saved": 0.0,
                       "overall_progress_percent": None, "nearest_deadline": None}
        gaps.append("No savings goals yet — goal progress is not assessed.")

    # ---- risk indicators (deterministic rules, evidence attached) ----
    risks = []
    if float(summary["net_balance"]) < 0:
        risks.append({"type": "negative_net_balance", "severity": "high",
                      "detail": "Total recorded expenses exceed total recorded income.",
                      "evidence": {"net_balance": float(summary["net_balance"])}})
    health = engine.health_score()
    if health.get("components", {}).get("buffer", {}).get("data_backed"):
        risks.append({"type": "buffer", "severity": "info",
                      "detail": health["components"]["buffer"]["note"],
                      "evidence": {"buffer_score": health["components"]["buffer"]["score"]}})
    if cv is not None and cv > 0.45:
        risks.append({"type": "spending_volatility", "severity": "medium",
                      "detail": "Monthly spending varies a lot month to month, which makes planning harder.",
                      "evidence": {"monthly_cv": round(cv, 3)}})
    if recurring_obligations["share_of_income_percent"] and recurring_obligations["share_of_income_percent"] > 10:
        risks.append({"type": "subscription_burden", "severity": "medium",
                      "detail": "Detected subscriptions consume more than 10% of average monthly income.",
                      "evidence": {"share_of_income_percent": recurring_obligations["share_of_income_percent"]}})
    if sources and sources[0]["share_percent"] > 80 and months_observed >= 2:
        risks.append({"type": "income_concentration", "severity": "medium",
                      "detail": f"Over 80% of income comes from one source ({sources[0]['merchant']}).",
                      "evidence": {"merchant": sources[0]["merchant"], "share_percent": sources[0]["share_percent"]}})
    if exp_values and avg_expense > 0 and exp_values[-1] > avg_expense * 1.25 and months_observed >= 3:
        risks.append({"type": "recent_spending_surge", "severity": "medium",
                      "detail": "The most recent month's spending is more than 25% above your monthly average.",
                      "evidence": {"latest_month_expense": exp_values[-1], "average_monthly_expense": round(avg_expense, 2)}})

    # ---- savings opportunities (deterministic, conservative) ----
    opportunities = []
    if subs["count"]:
        opportunities.append({"type": "subscription_review",
                              "detail": f"{subs['count']} detected subscriptions cost {obligations_monthly:,.2f} per month — reviewing ones you no longer use is the fastest saving.",
                              "estimated_monthly_saving": None})
    top_disc = next((c for c in cats if c["category"] in discretionary_names), None)
    if top_disc and months_observed:
        monthly_avg = top_disc["total"] / months_observed
        opportunities.append({"type": "category_reduction",
                              "detail": f"A 10% reduction in {top_disc['category']} (your largest discretionary category) would save about {monthly_avg * 0.10:,.2f} per month.",
                              "estimated_monthly_saving": round(monthly_avg * 0.10, 2)})

    # ---- predicted patterns (labelled forecasts, from the ML module) ----
    from app.ml.forecasting.model import forecast as ml_forecast
    f30 = ml_forecast(db, user_id, 30)
    predicted = {
        "next_30d_expense_estimate": f30.get("predicted_amount"),
        "expense_forecast_method": f30.get("method"),
        "expense_forecast_insufficient_data": bool(f30.get("insufficient_data")),
        "expected_monthly_income": round(avg_income, 2) if avg_income else None,
        "basis": "Expense estimate from the ML forecasting module; income is your observed monthly average (assumed, not guaranteed).",
    }

    return {
        "currency": cur, "insufficient_data": False,
        "income_patterns": income_patterns,
        "expense_patterns": expense_patterns,
        "spending_consistency": consistency,
        "recurring_obligations": recurring_obligations,
        "savings_behavior": savings_behavior,
        "budget_adherence": budget_adherence,
        "goals": goals_block,
        "risk_indicators": risks,
        "savings_opportunities": opportunities,
        "predicted_patterns": predicted,
        "health_score": health.get("score"),
        "health_grade": health.get("grade"),
        "data_gaps": gaps,
        "note": "Every figure is computed from your transaction records. Inferred patterns name their evidence; missing history is reported as a gap, never filled in.",
    }
