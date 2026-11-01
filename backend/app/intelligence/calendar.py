"""
Financial Calendar (Stage 4, Feature G).

Builds dated events for a range from the user's own records: the detected
salary pattern (assumed), detected subscriptions at their expected dates
(pattern, or confirmed once the user confirms them), recurring charge
groups, user-scheduled recurring transactions (confirmed), budget month
boundaries, goal deadlines, and the user's own payment reminders.
Everything is labelled with its certainty; nothing is invented. The same
event sources feed the cash-flow timeline, so calendar and forecast agree.
"""
import calendar as _cal
import statistics
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics.advanced import _FREQ_STEP_DAYS, _income_pattern, detect_subscriptions
from app.analytics.service import _dec, primary_currency
from app.models.models import Budget, FinancialGoal, PaymentReminder, RecurringTransaction, Transaction


def _occurrences_in_range(anchor: date, step_days: int, start: date, end: date):
    """Every occurrence of an `anchor`-based repeating date in [start, end)."""
    if step_days <= 0:
        return []
    d = anchor
    guard = 0
    while d >= start and guard < 600:
        d -= timedelta(days=step_days)
        guard += 1
    while d < start and guard < 1200:
        d += timedelta(days=step_days)
        guard += 1
    out = []
    while d < end and guard < 1800:
        out.append(d)
        d += timedelta(days=step_days)
        guard += 1
    return out


def _monthly_day_occurrences(day: int, start: date, end: date):
    """The given day-of-month (clamped to month length) in every month
    overlapping [start, end)."""
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) < end:
        d = date(y, m, min(day, _cal.monthrange(y, m)[1]))
        if start <= d < end:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _event(d, title, kind, amount, certainty, source):
    return {"date": d.isoformat(), "title": title, "kind": kind,
            "amount": round(float(amount), 2) if amount is not None else None,
            "certainty": certainty, "source": source}


def build_calendar_events(db: Session, user_id: int, start: date, end: date) -> dict:
    cur = primary_currency(db, user_id)
    events = []

    # Salary pattern (assumed income) — monthly pay lands on a day of the
    # month, so project by the detected typical day, not interval stepping.
    pattern = _income_pattern(db, user_id, cur)
    if pattern:
        for d in _monthly_day_occurrences(pattern["typical_day_of_month"], start, end):
            events.append(_event(d, f"{pattern['merchant']} salary (expected)", "income",
                                 pattern["amount"], "assumed", "income_pattern"))

    # Subscriptions (post-override)
    subs = detect_subscriptions(db, user_id)
    sub_keys = set()
    for sub in subs["subscriptions"]:
        sub_keys.add(sub["merchant_key"])
        step = _FREQ_STEP_DAYS.get(sub["frequency"], 30)
        if not sub.get("next_expected_date"):
            continue
        anchor = date.fromisoformat(sub["next_expected_date"])
        certainty = "confirmed" if sub["status"] == "confirmed" else "pattern"
        occ = (_monthly_day_occurrences(sub["typical_day_of_month"], start, end)
               if sub["frequency"] == "monthly" and sub.get("typical_day_of_month")
               else _occurrences_in_range(anchor, step, start, end))
        for d in occ:
            events.append(_event(d, f"{sub['merchant']} subscription", "subscription",
                                 sub["average_amount"], certainty, "subscription_detection"))

    # Recurring charge groups (is_recurring-flagged; cadence from real dates)
    rec_rows = db.query(Transaction.merchant, Transaction.category_name, Transaction.amount, Transaction.date).filter(
        Transaction.user_id == user_id, Transaction.is_recurring.is_(True),
        Transaction.type == "expense",
        func.coalesce(Transaction.currency, "INR") == cur).all()
    groups = defaultdict(list)
    for merchant, cat, amount, d in rec_rows:
        groups[((merchant or "").strip(), cat or "Uncategorized")].append((d, float(_dec(amount))))
    from app.analytics.advanced import merchant_key
    for (merchant, cat), items in groups.items():
        if merchant_key(merchant) in sub_keys or len(items) < 2:
            continue
        items.sort()
        gaps = [(items[i + 1][0] - items[i][0]).days for i in range(len(items) - 1)]
        med_gap = int(statistics.median(gaps)) if gaps else 0
        if not (5 <= med_gap <= 40):
            continue
        avg_amt = round(statistics.median([a for _, a in items]), 2)
        if 25 <= med_gap <= 35:
            # monthly cadence: project by typical day-of-month (a median
            # interval of 30.5 days must not drift the event off its day)
            typical_day = int(statistics.median([d.day for d, _ in items]))
            occ = _monthly_day_occurrences(typical_day, start, end)
        else:
            anchor = items[-1][0] + timedelta(days=med_gap)
            occ = _occurrences_in_range(anchor, med_gap, start, end)
        for d in occ:
            events.append(_event(d, f"{merchant or cat} (recurring)", "recurring",
                                 avg_amt, "pattern", "recurring_charges"))

    # User-scheduled recurring transactions (confirmed)
    for r in db.query(RecurringTransaction).filter(
            RecurringTransaction.user_id == user_id, RecurringTransaction.active.is_(True)).all():
        if r.next_date is None:
            continue
        step = _FREQ_STEP_DAYS.get(r.frequency or "monthly", 30)
        kind = "income" if r.type == "income" else "recurring"
        for d in _occurrences_in_range(r.next_date, step, start, end):
            events.append(_event(d, f"{r.merchant or r.description or 'Scheduled'} (scheduled)", kind,
                                 float(_dec(r.amount)), "confirmed", "user_recurring"))

    # Budget month boundaries
    months = set()
    d = date(start.year, start.month, 1)
    while d < end:
        months.add((d.year, d.month))
        d = date(d.year + (1 if d.month == 12 else 0), 1 if d.month == 12 else d.month + 1, 1)
    for (y, m) in sorted(months):
        budgets = db.query(Budget).filter(Budget.user_id == user_id, Budget.year == y, Budget.month == m).all()
        if budgets:
            total = sum(float(b.amount) for b in budgets)
            events.append(_event(date(y, m, 1), f"Budgets reset ({len(budgets)} budget(s))", "budget_reset",
                                 total, "confirmed", "budgets"))

    # Goal deadlines
    for g in db.query(FinancialGoal).filter(FinancialGoal.user_id == user_id).all():
        if g.deadline and start <= g.deadline < end:
            events.append(_event(g.deadline, f"Goal deadline: {g.name}", "goal",
                                 float(g.target_amount), "user", "goals"))

    # User payment reminders (with recurrence projection)
    step_map = {"weekly": 7, "monthly": 30, "yearly": 365}
    for r in db.query(PaymentReminder).filter(PaymentReminder.user_id == user_id).all():
        step = step_map.get(r.recurrence or "none", 0)
        dates = _occurrences_in_range(r.due_date, step, start, end) if step else (
            [r.due_date] if start <= r.due_date < end else [])
        for d in dates:
            events.append(_event(d, r.title, "reminder",
                                 float(_dec(r.amount)) if r.amount is not None else None,
                                 "user", f"reminder:{r.id}"))

    events.sort(key=lambda e: (e["date"], e["title"]))
    income_total = round(sum(e["amount"] or 0 for e in events if e["kind"] == "income"), 2)
    obligations_total = round(sum(e["amount"] or 0 for e in events
                                  if e["kind"] in ("subscription", "recurring", "reminder")), 2)
    return {"start": start.isoformat(), "end": end.isoformat(), "currency": cur,
            "events": events, "count": len(events),
            "summary": {"expected_income": income_total, "expected_obligations": obligations_total},
            "note": "Events are computed from your records and labelled by certainty: confirmed/user entries are ones you set or approved; pattern entries are detected; assumed income is a detected pattern, not a guarantee."}


def month_range(year: int, month: int):
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    return start, end
