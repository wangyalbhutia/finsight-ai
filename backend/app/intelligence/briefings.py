"""
Proactive briefings (Stage 7). Generates notification items from the
user's real data using the same deterministic services as the dashboard:
budget month-end forecast, smart insights, and goal progress. Items are
deduplicated by (kind, subject, week) so opening the briefing twice
never spams duplicates. Nothing here invents numbers.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics.advanced import budget_forecast, smart_insights
from app.models.models import FinancialGoal, Notification


def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def generate_briefings(db: Session, user_id: int) -> int:
    today = date.today()
    wk = _week_key(today)
    existing = {n.dedupe_key for n in db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.created_at >= (today - timedelta(days=7)).isoformat()).all()}
    created = 0

    def add(kind, severity, title, body, subject):
        nonlocal created
        key = f"{kind}:{subject}:{wk}"
        if key in existing:
            return
        db.add(Notification(user_id=user_id, kind=kind, severity=severity,
                            title=title, body=body, dedupe_key=key))
        existing.add(key)
        created += 1

    try:
        bf = budget_forecast(db, user_id)
        for item in bf.get("budgets", []):
            if item.get("risk") in ("high", "exceeded"):
                cat = item.get("category_name") or "A budget"
                add("budget_risk", "warning",
                    f"{cat} budget at risk this month",
                    f"Spent ₹{item['spent']:,.2f} of ₹{item['limit_amount']:,.2f}; at the current pace the month ends near ₹{item['projected_month_end_spend']:,.2f} ({item['projected_utilisation_percent']:.0f}% of the limit). Safe daily allowance from here: ₹{item['safe_daily_allowance']:,.2f}.",
                    str(cat))
    except Exception:
        pass

    try:
        ins = smart_insights(db, user_id)
        for i in ins.get("insights", []):
            if i.get("severity") == "warning":
                add(f"insight:{i.get('type')}", "warning", i.get("title", "Spending insight"),
                    i.get("detail", ""), str(i.get("type")))
    except Exception:
        pass

    for g in db.query(FinancialGoal).filter(FinancialGoal.user_id == user_id).all():
        if g.target_amount and float(g.target_amount) > 0:
            pct = float(g.current_amount or 0) / float(g.target_amount) * 100
            if pct >= 75 and pct < 100:
                add("goal_milestone", "positive",
                    f"Goal '{g.name}' is {pct:.0f}% funded",
                    f"You have saved ₹{float(g.current_amount or 0):,.2f} of ₹{float(g.target_amount):,.2f}.",
                    f"goal:{g.id}")

    if created:
        db.commit()
    return created
