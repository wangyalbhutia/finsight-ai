"""
Analytics — SQL-aggregated, Decimal arithmetic (no float drift).

Stage 2 (Financial Intelligence Engine): all aggregations are computed with
SQL GROUP BY queries instead of loading every transaction into Python.
Semantics are unchanged from the original implementation:

Rules (approved Phase 1, do not change):
- transfers excluded from income/expense
- refunds offset expenses
Multi-currency: a user's primary currency is User.preferred_currency
(default INR). Headline totals sum ONLY transactions in that currency.
Transactions in other currencies are NOT silently added; they appear
separately in totals_by_currency.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Transaction, User

D0 = Decimal("0")


def primary_currency(db, user_id):
    u = db.query(User).filter(User.id == user_id).first()
    return (u.preferred_currency or u.currency or "INR") if u else "INR"


def _dec(v):
    return Decimal(str(v)) if not isinstance(v, Decimal) else v


def _range(year, month):
    """[start, end) date range for a year[/month] filter, or (None, None)."""
    if year is None:
        return None, None
    if month is not None:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    else:
        start, end = date(year, 1, 1), date(year + 1, 1, 1)
    return start, end


def _apply_range(q, year, month):
    start, end = _range(year, month)
    if start is not None:
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    return q


def _totals_by_currency_type(db, user_id, year=None, month=None):
    """One grouped query: {(currency, type): (Decimal sum, count)}."""
    q = db.query(Transaction.currency, Transaction.type,
                 func.sum(Transaction.amount), func.count(Transaction.id)
                 ).filter(Transaction.user_id == user_id)
    q = _apply_range(q, year, month)
    out = {}
    for cur, type_, total, count in q.group_by(Transaction.currency, Transaction.type).all():
        out[(cur or "INR", type_)] = (_dec(total or 0), count)
    return out


def compute_summary(db: Session, user_id: int, year: int = None, month: int = None):
    cur = primary_currency(db, user_id)
    grouped = _totals_by_currency_type(db, user_id, year, month)

    by_cur = {}
    for (c, type_), (total, _count) in grouped.items():
        by_cur.setdefault(c, {"income": D0, "expense": D0})
        if type_ == "income":
            by_cur[c]["income"] += total
        elif type_ == "expense":
            by_cur[c]["expense"] += total
        elif type_ == "refund":
            by_cur[c]["expense"] -= total
    totals_by_currency = {c: {"total_income": float(v["income"]), "total_expense": float(max(D0, v["expense"]))}
                          for c, v in by_cur.items()}

    def g(type_):
        return grouped.get((cur, type_), (D0, 0))[0]

    income = g("income")
    refunds = g("refund")
    expense_raw = g("expense")
    expense = max(D0, expense_raw - refunds)
    net = income - expense
    savings_rate = (net / income * Decimal("100")) if income > 0 else D0
    count = sum(cnt for (c, _t), (_s, cnt) in grouped.items() if c == cur)
    return {
        "total_income": float(income), "total_expense": float(expense), "total_expenditure": float(expense),
        "net_balance": float(net), "net": float(net), "savings_rate": float(round(savings_rate, 2)),
        "transaction_count": count, "refund_total": float(refunds),
        "currency": cur, "primary_currency": cur, "totals_by_currency": totals_by_currency,
    }


def category_breakdown(db: Session, user_id: int, year: int = None, month: int = None):
    cur = primary_currency(db, user_id)
    label = func.coalesce(func.nullif(Transaction.category_name, ""), "Uncategorized")
    q = db.query(label, func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur)
    q = _apply_range(q, year, month)
    rows = q.group_by(label).all()
    out = [{"category": name, "category_name": name, "total": float(_dec(total or 0)),
            "amount": float(_dec(total or 0))} for name, total in rows]
    out.sort(key=lambda x: -x["total"])
    return out


def daily_totals(db: Session, user_id: int, currency: str, type_: str = "expense"):
    """{date: Decimal} of daily sums for one type/currency — one grouped query."""
    q = db.query(Transaction.date, func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id, Transaction.type == type_,
        func.coalesce(Transaction.currency, "INR") == currency)
    return {d: _dec(total or 0) for d, total in q.group_by(Transaction.date).order_by(Transaction.date).all()}


def trends(db: Session, user_id: int):
    cur = primary_currency(db, user_id)
    daily_map = daily_totals(db, user_id, cur, "expense")
    income_map = daily_totals(db, user_id, cur, "income")
    # Points carry income + expense alongside the legacy `total` (expense)
    # so chart consumers can plot both series directly.
    daily = [{"date": d.isoformat(), "total": float(v), "expense": float(v),
              "income": float(income_map.get(d, D0))} for d, v in sorted(daily_map.items())]
    weekly, weekly_inc = defaultdict(lambda: D0), defaultdict(lambda: D0)
    monthly, monthly_inc = defaultdict(lambda: D0), defaultdict(lambda: D0)
    for d, v in daily_map.items():
        weekly[f"{d.year}-W{d.isocalendar()[1]:02d}"] += v
        monthly[d.strftime("%Y-%m")] += v
    for d, v in income_map.items():
        weekly_inc[f"{d.year}-W{d.isocalendar()[1]:02d}"] += v
        monthly_inc[d.strftime("%Y-%m")] += v
    weekly_list = [{"week": k, "total": float(v), "expense": float(v),
                    "income": float(weekly_inc.get(k, D0))} for k, v in sorted(weekly.items())]
    monthly_list = [{"month": k, "total": float(v), "expense": float(v),
                     "income": float(monthly_inc.get(k, D0))} for k, v in sorted(monthly.items())]
    return {
        "daily": daily, "daily_spending": daily,
        "weekly": weekly_list, "weekly_patterns": weekly_list,
        "monthly": monthly_list, "monthly_spending": monthly_list,
    }


def monthly_comparison(db, user_id):
    return trends(db, user_id)["monthly"]


def recurring_expenses(db: Session, user_id: int):
    cur = primary_currency(db, user_id)
    q = db.query(Transaction.merchant, Transaction.category_name,
                 func.sum(Transaction.amount), func.count(Transaction.id)).filter(
        Transaction.user_id == user_id, Transaction.is_recurring.is_(True),
        func.coalesce(Transaction.currency, "INR") == cur)
    rows = q.group_by(Transaction.merchant, Transaction.category_name).order_by(func.min(Transaction.id)).all()
    return [{"name": (m or c or "Unknown"), "merchant": (m or c or "Unknown"),
             "category_name": (m or c or "Unknown"), "total": float(_dec(total or 0)), "count": count}
            for m, c, total, count in rows]


def dashboard(db: Session, user_id: int, year: int = None, month: int = None):
    s = compute_summary(db, user_id, year, month)
    cats = category_breakdown(db, user_id, year, month)
    tr = trends(db, user_id)
    recent_rows = db.query(Transaction).filter(
        Transaction.user_id == user_id).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(10).all()
    recent = [{"id": t.id, "type": t.type, "amount": float(t.amount),
               "currency": getattr(t, "currency", "INR") or "INR", "category_name": t.category_name,
               "merchant": t.merchant, "description": t.description, "date": t.date.isoformat()}
              for t in recent_rows]
    return {**s, "category_breakdown": cats, "top_categories": cats[:5], "highest_expenditure_categories": cats[:5],
            **tr, "monthly_comparison": tr["monthly"], "recurring_expenses": recurring_expenses(db, user_id),
            "recent_transactions": recent}
