from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.models import *
from app.schemas.schemas import BudgetIn, CategorizeIn, ChatIn, SimulatorIn, SimulatorCompareIn, CategoryIn, GoalIn, RecurringIn, AffordIn, SubscriptionOverrideIn, ReminderIn, TrajectoryIn
from app.analytics.service import dashboard, compute_summary, category_breakdown, trends, recurring_expenses, monthly_comparison
from app.ml.categorization.model import suggest_category
from app.ml.forecasting.model import forecast, forecast_all, evaluate_models, _daily_series, rolling_origin_evaluation, category_evaluations
from app.ml.anomaly_detection.model import detect_anomalies
from app.agents.orchestrator import route as agent_route, simulate
from app.agents.recommendation_agent import recommendations
from app.analytics.advanced import financial_health_score, smart_insights, detect_subscriptions, budget_forecast, cashflow_projection, affordability
from app.intelligence.engine import get_engine
from app.agents.tools import READ_ONLY_TOOLS
from decimal import Decimal
import csv, io
from datetime import date

router = APIRouter(tags=["resources"])

# ---------- Analytics ----------
@router.get("/analytics/dashboard")
def get_dashboard(year: int = None, month: int = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return get_engine(db, current.id).dashboard(year, month)

@router.get("/calendar/events")
def get_calendar_events(start: date = None, end: date = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.intelligence.calendar import build_calendar_events, month_range
    if start is None or end is None:
        today = date.today()
        start, end = month_range(today.year, today.month)
    if end <= start:
        raise HTTPException(422, "end must be after start")
    return build_calendar_events(db, current.id, start, end)

@router.get("/calendar/reminders")
def list_reminders(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.query(PaymentReminder).filter(PaymentReminder.user_id == current.id).order_by(PaymentReminder.due_date).all()
    return [{"id": r.id, "title": r.title, "amount": float(r.amount) if r.amount is not None else None,
             "due_date": r.due_date.isoformat(), "recurrence": r.recurrence,
             "category_name": r.category_name, "notes": r.notes} for r in rows]

@router.post("/calendar/reminders", status_code=201)
def create_reminder(data: ReminderIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if data.recurrence not in ("none", "weekly", "monthly", "yearly"):
        raise HTTPException(422, "recurrence must be none, weekly, monthly or yearly")
    r = PaymentReminder(user_id=current.id, title=data.title, amount=data.amount,
                        due_date=data.due_date, recurrence=data.recurrence,
                        category_name=data.category_name or "", notes=data.notes or "")
    db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id, "title": r.title, "due_date": r.due_date.isoformat(), "recurrence": r.recurrence}

@router.put("/calendar/reminders/{reminder_id}")
def update_reminder(reminder_id: int, data: ReminderIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    r = db.query(PaymentReminder).filter(PaymentReminder.id == reminder_id, PaymentReminder.user_id == current.id).first()
    if r is None:
        raise HTTPException(404, "Reminder not found")
    if data.recurrence not in ("none", "weekly", "monthly", "yearly"):
        raise HTTPException(422, "recurrence must be none, weekly, monthly or yearly")
    r.title, r.amount, r.due_date, r.recurrence = data.title, data.amount, data.due_date, data.recurrence
    r.category_name, r.notes = data.category_name or "", data.notes or ""
    db.commit()
    return {"id": r.id, "title": r.title, "due_date": r.due_date.isoformat(), "recurrence": r.recurrence}

@router.delete("/calendar/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    r = db.query(PaymentReminder).filter(PaymentReminder.id == reminder_id, PaymentReminder.user_id == current.id).first()
    if r is None:
        raise HTTPException(404, "Reminder not found")
    db.delete(r); db.commit()
    return {"removed": True, "id": reminder_id}

@router.get("/memories")
def list_memories(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rows = db.query(UserMemory).filter(UserMemory.user_id == current.id).order_by(UserMemory.category, UserMemory.key).all()
    return [{"id": m.id, "category": m.category, "key": m.key, "value": m.value,
             "updated_at": m.updated_at.isoformat() if m.updated_at else None} for m in rows]

@router.post("/memories", status_code=201)
def upsert_memory(data: dict, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    category = (data.get("category") or "preference").strip()
    key = (data.get("key") or "").strip()
    value = (data.get("value") or "").strip()
    if category not in ("preference", "merchant_correction", "life_event", "note"):
        raise HTTPException(422, "category must be preference, merchant_correction, life_event or note")
    if not key or not value:
        raise HTTPException(422, "key and value are required")
    row = db.query(UserMemory).filter(UserMemory.user_id == current.id,
                                      UserMemory.category == category, UserMemory.key == key).first()
    if row is None:
        row = UserMemory(user_id=current.id, category=category, key=key)
        db.add(row)
    row.value = value
    db.commit(); db.refresh(row)
    return {"id": row.id, "category": row.category, "key": row.key, "value": row.value}

@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = db.query(UserMemory).filter(UserMemory.id == memory_id, UserMemory.user_id == current.id).first()
    if row is None:
        raise HTTPException(404, "Memory not found")
    db.delete(row); db.commit()
    return {"removed": True, "id": memory_id}

@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.intelligence.briefings import generate_briefings
    generate_briefings(db, current.id)  # lazy, deduplicated weekly briefing
    rows = db.query(Notification).filter(Notification.user_id == current.id).order_by(Notification.is_read, Notification.created_at.desc()).limit(50).all()
    return {"notifications": [{"id": n.id, "kind": n.kind, "severity": n.severity, "title": n.title,
                               "body": n.body, "is_read": bool(n.is_read),
                               "created_at": n.created_at.isoformat() if n.created_at else None} for n in rows],
            "unread_count": sum(1 for n in rows if not n.is_read)}

@router.post("/notifications/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.id == notif_id, Notification.user_id == current.id).first()
    if n is None:
        raise HTTPException(404, "Notification not found")
    n.is_read = True; db.commit()
    return {"id": n.id, "is_read": True}

@router.delete("/notifications/{notif_id}")
def delete_notification(notif_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.id == notif_id, Notification.user_id == current.id).first()
    if n is None:
        raise HTTPException(404, "Notification not found")
    db.delete(n); db.commit()
    return {"removed": True, "id": notif_id}

@router.get("/account/export")
def account_export(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Stage 7: full data portability — everything FinSight holds for the
    user, as one JSON download."""
    import json as _json
    def rows(model, order=None):
        q = db.query(model).filter(model.user_id == current.id)
        if order is not None:
            q = q.order_by(order)
        return q.all()
    txns = rows(Transaction, Transaction.date)
    payload = {
        "exported_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "user": {"id": current.id, "email": current.email, "full_name": getattr(current, "full_name", None)},
        "transactions": [{"date": t.date.isoformat(), "type": t.type, "amount": float(t.amount),
                          "currency": t.currency or "INR", "category_name": t.category_name,
                          "merchant": t.merchant, "description": t.description, "notes": t.notes or "",
                          "is_recurring": bool(t.is_recurring)} for t in txns],
        "budgets": [{"category_name": b.category_name, "amount": float(b.amount), "month": b.month, "year": b.year} for b in rows(Budget)],
        "goals": [{"name": g.name, "target_amount": float(g.target_amount), "current_amount": float(g.current_amount or 0),
                   "deadline": g.deadline.isoformat() if g.deadline else None} for g in rows(FinancialGoal)],
        "recurring": [{"merchant": r.merchant, "amount": float(r.amount), "frequency": r.frequency,
                       "next_date": r.next_date.isoformat() if r.next_date else None} for r in rows(RecurringTransaction)],
        "subscription_overrides": [{"merchant": o.merchant, "merchant_key": o.merchant_key, "status": o.status} for o in rows(SubscriptionOverride)],
        "payment_reminders": [{"title": r.title, "amount": float(r.amount) if r.amount is not None else None,
                               "due_date": r.due_date.isoformat(), "recurrence": r.recurrence} for r in rows(PaymentReminder)],
        "memories": [{"category": m.category, "key": m.key, "value": m.value} for m in rows(UserMemory)],
        "statement_imports": [{"filename": si.filename, "format_detected": si.format_detected, "total_rows": si.total_rows,
                               "accepted": si.accepted, "duplicates": si.duplicates, "rejected": si.rejected} for si in rows(StatementImport)],
        "health_score_snapshots": [{"date": s2.snapshot_date.isoformat() if s2.snapshot_date else None, "score": float(s2.score), "grade": s2.grade} for s2 in rows(HealthScoreSnapshot)],
    }
    return Response(content=_json.dumps(payload, indent=2), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=finsight-export.json"})

@router.delete("/account")
def delete_account(data: dict, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Stage 7: permanent account + data deletion. Requires the explicit
    confirmation string; deletes every user-owned row, then the user."""
    if (data or {}).get("confirm") != "DELETE":
        raise HTTPException(422, 'Type DELETE to confirm permanent account deletion')
    uid = current.id
    for model in (Transaction, Budget, FinancialGoal, RecurringTransaction, Category, AnomalyAlert,
                  Prediction, HealthScoreSnapshot, SubscriptionOverride, PaymentReminder,
                  StatementImport, UserMemory, Notification, AuditLog):
        try:
            db.query(model).filter(model.user_id == uid).delete(synchronize_session=False)
        except Exception:
            db.rollback()
    user = db.query(User).filter(User.id == uid).first()
    if user is not None:
        db.delete(user)
    db.commit()
    return {"deleted": True}

@router.get("/intelligence/overview")
def get_intelligence_overview(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # Central Financial Intelligence Engine facade: typed envelope with
    # data freshness + versions around the shared analytical payload.
    return get_engine(db, current.id).overview()

@router.get("/analytics/summary")
def get_summary(year: int = None, month: int = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return compute_summary(db, current.id, year, month)

@router.get("/analytics/health-score")
def get_health_score(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # Stage 3: snapshot-on-read (one stored reading per user per day) so
    # score history and change explanations have real data.
    from app.analytics.advanced import snapshot_health_score
    result = get_engine(db, current.id).health_score()
    snapshot_health_score(db, current.id, result)
    return result

@router.get("/analytics/health-score/history")
def get_health_score_history(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.analytics.advanced import health_score_history
    return health_score_history(db, current.id)

@router.get("/intelligence/profile")
def get_intelligence_profile(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # Digital Twin profile, wrapped in the engine's typed envelope.
    engine = get_engine(db, current.id)
    return engine.envelope("fact", engine.profile())

@router.get("/analytics/cashflow-timeline")
def get_cashflow_timeline(horizon_days: int = 30, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    try:
        return get_engine(db, current.id).cashflow_timeline(horizon_days)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.get("/challenges")
def get_challenges(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.analytics.advanced import weekly_challenges
    return weekly_challenges(db, current.id)

@router.get("/analytics/insights")
def get_insights(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return smart_insights(db, current.id)

@router.post("/analytics/subscriptions/override")
def post_subscription_override(data: SubscriptionOverrideIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.analytics.advanced import set_subscription_override
    try:
        return set_subscription_override(db, current.id, data.merchant, data.status,
                                         data.custom_amount, data.custom_frequency, data.custom_next_date)
    except ValueError as e:
        raise HTTPException(422, str(e))

@router.delete("/analytics/subscriptions/override/{merchant_key}")
def delete_subscription_override(merchant_key: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.analytics.advanced import remove_subscription_override
    if not remove_subscription_override(db, current.id, merchant_key):
        raise HTTPException(404, "Override not found")
    return {"removed": True, "merchant_key": merchant_key}

@router.get("/analytics/subscriptions")
def get_subscriptions(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return detect_subscriptions(db, current.id)

@router.get("/dashboard")
def get_dashboard_alias(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return dashboard(db, current.id)

@router.get("/analytics/categories")
def get_cats(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return category_breakdown(db, current.id)

@router.get("/analytics/trends")
def get_trends(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return trends(db, current.id)

@router.get("/analytics/recurring")
def get_recurring(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return recurring_expenses(db, current.id)

@router.get("/analytics/weekly-pattern")
def get_weekly_pattern(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return trends(db, current.id)["weekly"]

@router.get("/analytics/monthly-comparison")
def get_monthly_comparison(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return monthly_comparison(db, current.id)

# ---------- Categories ----------
@router.post("/categories", status_code=201)
def create_category(data: CategoryIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    c = Category(user_id=current.id, name=data.name, type=data.type, icon=data.icon); db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "user_id": c.user_id, "name": c.name, "type": c.type, "icon": c.icon}

@router.get("/categories")
def list_categories(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    cats = db.query(Category).filter((Category.user_id == current.id) | (Category.user_id == None)).all()
    return [{"id": c.id, "user_id": c.user_id, "name": c.name, "type": c.type, "icon": c.icon} for c in cats]

@router.post("/categories/suggest")
def suggest_category_alias(data: CategorizeIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # Stage 7: the user's own merchant correction always wins over the model.
    if data.merchant:
        mem = db.query(UserMemory).filter(
            UserMemory.user_id == current.id, UserMemory.category == "merchant_correction",
            UserMemory.key == data.merchant.strip().lower()).first()
        if mem is not None:
            return {"category": mem.value, "confidence": 1.0, "source": "your saved correction"}
    return suggest_category(data.description, data.merchant)

@router.get("/categories/suggest")
def suggest_category_alias_get(description: str = "", merchant: str = "", current: User = Depends(get_current_user)):
    return suggest_category(description, merchant)

@router.get("/categories/{cid}")
def get_category(cid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    c = db.query(Category).filter(Category.id == cid, Category.user_id == current.id).first()
    if not c: raise HTTPException(404, "Category not found")
    return {"id": c.id, "user_id": c.user_id, "name": c.name, "type": c.type, "icon": c.icon}

@router.delete("/categories/{cid}")
def delete_category(cid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    c = db.query(Category).filter(Category.id == cid, Category.user_id == current.id).first()
    if not c: raise HTTPException(404, "Category not found")
    db.delete(c); db.commit(); return {"detail": "Deleted"}

# ---------- Accounts / Goals / Recurring ----------
@router.post("/accounts", status_code=201)
def create_account(data: dict, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    a = Account(user_id=current.id, name=data.get("name","Main"), type=data.get("type","bank"), currency=data.get("currency","INR"), balance=Decimal(str(data.get("balance",0))))
    db.add(a); db.commit(); db.refresh(a); return {"id": a.id, "user_id": a.user_id, "name": a.name, "type": a.type, "currency": a.currency, "balance": float(a.balance)}
@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return [{"id": a.id, "user_id": a.user_id, "name": a.name, "type": a.type, "currency": a.currency, "balance": float(a.balance)} for a in db.query(Account).filter(Account.user_id==current.id).all()]

@router.post("/goals", status_code=201)
def create_goal(data: GoalIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    g = FinancialGoal(user_id=current.id, name=data.name, target_amount=data.target_amount, current_amount=data.current_amount, deadline=data.deadline); db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id, "user_id": g.user_id, "name": g.name, "target_amount": float(g.target_amount), "current_amount": float(g.current_amount)}
@router.get("/goals")
def list_goals(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return [{"id": g.id, "user_id": g.user_id, "name": g.name, "target_amount": float(g.target_amount), "current_amount": float(g.current_amount)} for g in db.query(FinancialGoal).filter(FinancialGoal.user_id==current.id).all()]
@router.get("/goals/{gid}")
def get_goal(gid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    g = db.query(FinancialGoal).filter(FinancialGoal.id==gid, FinancialGoal.user_id==current.id).first()
    if not g: raise HTTPException(404, "Goal not found")
    return {"id": g.id, "user_id": g.user_id, "name": g.name, "target_amount": float(g.target_amount), "current_amount": float(g.current_amount)}

@router.post("/recurring", status_code=201)
def create_recurring(data: RecurringIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    r = RecurringTransaction(user_id=current.id, category_name=data.category_name, type=data.type, amount=data.amount, merchant=data.merchant, description=data.description, frequency=data.frequency, next_date=data.next_date); db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id, "user_id": r.user_id, "category_name": r.category_name, "amount": float(r.amount), "frequency": r.frequency}
@router.get("/recurring")
def list_recurring(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return [{"id": r.id, "user_id": r.user_id, "category_name": r.category_name, "amount": float(r.amount), "frequency": r.frequency, "merchant": r.merchant} for r in db.query(RecurringTransaction).filter(RecurringTransaction.user_id==current.id).all()]

# ---------- Budgets ----------
def budget_out(db, b):
    # spent in budget month/year, category or overall, primary currency only via category_breakdown logic simplified
    txns = db.query(Transaction).filter(Transaction.user_id==b.user_id, Transaction.type=="expense").all()
    spent = sum(float(t.amount) for t in txns if t.date.year==b.year and t.date.month==b.month and (b.category_name=="Overall" or t.category_name==b.category_name))
    amt = float(b.amount); util = (spent/amt*100) if amt else 0
    level = None
    for th in (100,90,75,50):
        if util >= th: level = f"{th}%"; break
    return {"id": b.id, "user_id": b.user_id, "category_name": b.category_name, "category": b.category_name, "name": b.category_name, "amount": amt, "limit_amount": amt, "month": b.month, "year": b.year,
            "spent": round(spent,2), "remaining": round(amt-spent,2), "utilisation": round(util,2), "utilization": round(util,2), "alert_level": level, "alert_threshold": level}

@router.post("/budgets", status_code=201)
def create_budget(data: BudgetIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    b = Budget(user_id=current.id, category_name=data.category_name, amount=data.amount, month=data.month, year=data.year); db.add(b); db.commit(); db.refresh(b); return budget_out(db,b)
@router.get("/budgets")
def list_budgets(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return [budget_out(db,b) for b in db.query(Budget).filter(Budget.user_id==current.id).all()]
@router.get("/budgets/alerts")
def budget_alerts(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    outs=[budget_out(db,b) for b in db.query(Budget).filter(Budget.user_id==current.id).all()]
    alerts=[]
    for o in outs:
        if o["utilisation"]>=50: alerts.append({**o, "warning": f"Budget {o['category_name']} at {o['utilisation']:.1f}% ({o['alert_level']} threshold)"})
        # forecast-based overrun
        f=forecast(db, current.id, 30)
        if not f["insufficient_data"] and f["predicted_amount"] and o["category_name"]=="Overall" and o["spent"]+f["predicted_amount"]>o["amount"]:
            alerts.append({**o, "warning": "Forecast-based warning: projected spending may exceed budget", "forecast_predicted_30d": f["predicted_amount"]})
    return {"alerts": alerts, "budgets": outs}
@router.get("/budgets/recommendations")
def budget_recs(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return {"recommendations": recommendations(db, current.id)}
@router.get("/budgets/status")
def budget_status(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return [budget_out(db, b) for b in db.query(Budget).filter(Budget.user_id == current.id).all()]

@router.get("/budgets/forecast")
def get_budget_forecast(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return budget_forecast(db, current.id)

@router.get("/budgets/{bid}")
def get_budget(bid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    b=db.query(Budget).filter(Budget.id==bid, Budget.user_id==current.id).first()
    if not b: raise HTTPException(404, "Budget not found")
    return budget_out(db,b)
@router.put("/budgets/{bid}")
def update_budget(bid: int, data: BudgetIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    b=db.query(Budget).filter(Budget.id==bid, Budget.user_id==current.id).first()
    if not b: raise HTTPException(404, "Budget not found")
    b.category_name=data.category_name; b.amount=data.amount; b.month=data.month; b.year=data.year; db.commit(); return budget_out(db,b)
@router.delete("/budgets/{bid}")
def delete_budget(bid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    b=db.query(Budget).filter(Budget.id==bid, Budget.user_id==current.id).first()
    if not b: raise HTTPException(404, "Budget not found")
    db.delete(b); db.commit(); return {"detail":"Deleted"}

# ---------- ML ----------
@router.post("/ml/categorize")
def categorize(data: CategorizeIn, current: User = Depends(get_current_user)):
    return suggest_category(data.description, data.merchant)
@router.get("/ml/categorize")
def categorize_get(description: str = "", merchant: str = "", current: User = Depends(get_current_user)):
    return suggest_category(description, merchant)

@router.get("/ml/forecast")
def get_forecast(days: int = 30, horizon_days: int = None, category_name: str = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return forecast(db, current.id, horizon_days or days, category_name)
@router.post("/ml/forecast")
def post_forecast(payload: dict = {}, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return forecast(db, current.id, int(payload.get("horizon_days") or payload.get("days") or 30), payload.get("category_name"))
@router.get("/ml/forecast/all")
def get_forecast_all(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return forecast_all(db, current.id)
@router.get("/predictions/forecast")
def pred_forecast(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return forecast_all(db, current.id)
@router.get("/ml/evaluation")
@router.get("/predictions/evaluation")
def evaluation(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    series=_daily_series(db, current.id)
    ev=evaluate_models(series)
    ro=rolling_origin_evaluation(series)
    return {"evaluation": ev, "models": ev.get("models",{}), "split": ev.get("split",{}), "insufficient_data": ev.get("insufficient_data", True), "model_version":"exp_smoothing_v1",
            "rolling_origin": ro, "best_model_rolling_origin": ro.get("best_model"),
            "per_category": category_evaluations(db, current.id),
            "evaluation_note": "Models are compared on chronological hold-outs and rolling origins only — time-series data is never shuffled, and per-category results are reported only where enough history exists."}
@router.get("/predictions")
def list_predictions(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    preds=db.query(Prediction).filter(Prediction.user_id==current.id).order_by(Prediction.created_at.desc()).all()
    return [{"id":p.id,"user_id":p.user_id,"horizon_days":p.horizon_days,"predicted_amount":p.predicted_amount,"lower_bound":p.lower_bound,"upper_bound":p.upper_bound,"category_name":p.category_name,"model_version":p.model_version,"mae":p.mae,"rmse":p.rmse,"mape":p.mape,"created_at":p.created_at.isoformat() if p.created_at else None} for p in preds]
@router.get("/predictions/{pid}")
def get_prediction(pid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p=db.query(Prediction).filter(Prediction.id==pid, Prediction.user_id==current.id).first()
    if not p: raise HTTPException(404, "Prediction not found")
    return {"id":p.id,"user_id":p.user_id,"horizon_days":p.horizon_days,"predicted_amount":p.predicted_amount,"category_name":p.category_name,"model_version":p.model_version}

# anomalies
@router.post("/ml/anomalies/detect")
@router.get("/ml/anomalies/detect")
def detect(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    anomalies=detect_anomalies(db, current.id, persist=True)
    alerts=db.query(AnomalyAlert).filter(AnomalyAlert.user_id==current.id).all()
    return {"anomalies": anomalies, "count": len(anomalies), "alerts":[{"id":a.id,"user_id":a.user_id,"transaction_id":a.transaction_id,"severity":a.severity,"reason":a.reason,"score":a.score,"anomaly_type":a.anomaly_type,"status":a.status} for a in alerts]}
@router.get("/anomalies")
@router.get("/ml/anomalies")
def list_anomalies(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # ensure detection has run at least reflects DB; return persisted alerts
    alerts=db.query(AnomalyAlert).filter(AnomalyAlert.user_id==current.id).all()
    return [{"id":a.id,"user_id":a.user_id,"transaction_id":a.transaction_id,"severity":a.severity,"reason":a.reason,"score":a.score,"anomaly_type":a.anomaly_type,"status":a.status,"created_at":a.created_at.isoformat() if a.created_at else None} for a in alerts]
@router.get("/anomalies/{aid}")
def get_anomaly(aid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    a=db.query(AnomalyAlert).filter(AnomalyAlert.id==aid, AnomalyAlert.user_id==current.id).first()
    if not a: raise HTTPException(404, "Anomaly not found")
    return {"id":a.id,"user_id":a.user_id,"transaction_id":a.transaction_id,"severity":a.severity,"reason":a.reason,"score":a.score,"anomaly_type":a.anomaly_type,"status":a.status}
@router.patch("/anomalies/{aid}")
@router.post("/anomalies/{aid}/acknowledge")
def ack_anomaly(aid: int, payload: dict = {}, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    a=db.query(AnomalyAlert).filter(AnomalyAlert.id==aid, AnomalyAlert.user_id==current.id).first()
    if not a: raise HTTPException(404, "Anomaly not found")
    status_val=payload.get("status") if isinstance(payload, dict) else None
    a.status = status_val if status_val in ("acknowledged","dismissed","open") else "acknowledged"
    db.commit(); return {"id":a.id,"status":a.status}
@router.post("/anomalies/{aid}/dismiss")
def dismiss_anomaly(aid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    a=db.query(AnomalyAlert).filter(AnomalyAlert.id==aid, AnomalyAlert.user_id==current.id).first()
    if not a: raise HTTPException(404, "Anomaly not found")
    a.status="dismissed"; db.commit(); return {"id":a.id,"status":a.status}

# ---------- Simulator ----------
@router.post("/simulator")
@router.post("/simulator/run")
def run_simulator(data: SimulatorIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return simulate(db, current.id, data.category_name, data.reduction_percent)
@router.post("/simulator/compare")
def compare_simulator(data: SimulatorCompareIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    results=[simulate(db, current.id, s.category_name, s.reduction_percent) for s in data.scenarios]
    return {"scenarios": results, "results": results}

# ---------- Assistant ----------
@router.post("/assistant/chat")
def chat(data: ChatIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # data.message is the user's own instruction; transaction text is never passed raw — agents use aggregates only.
    if data.conversation_id:
        conv=db.query(AIConversation).filter(AIConversation.id==data.conversation_id, AIConversation.user_id==current.id).first()
        if not conv: raise HTTPException(404, "Conversation not found")
    else:
        conv=AIConversation(user_id=current.id, title=data.message[:60]); db.add(conv); db.commit(); db.refresh(conv)
    result=agent_route(db, current.id, data.message)
    text=result.get("text") or result.get("response") or ""
    db.add(AIMessage(conversation_id=conv.id, role="user", content=data.message))
    db.add(AIMessage(conversation_id=conv.id, role="assistant", content=text)); db.commit()
    return {"response": text, "reply": text, "agent": result.get("agent","analytics"), "conversation_id": conv.id, "tools_used": result.get("tools_used",[]), "available_tools": READ_ONLY_TOOLS, "read_only": True, "data": result}
@router.get("/assistant/conversations")
def list_convs(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    convs=db.query(AIConversation).filter(AIConversation.user_id==current.id).all()
    return [{"id":c.id,"user_id":c.user_id,"title":c.title,"created_at":c.created_at.isoformat() if c.created_at else None} for c in convs]
@router.get("/assistant/conversations/{cid}")
def get_conv(cid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    conv=db.query(AIConversation).filter(AIConversation.id==cid, AIConversation.user_id==current.id).first()
    if not conv: raise HTTPException(404, "Conversation not found")
    msgs=db.query(AIMessage).filter(AIMessage.conversation_id==cid).order_by(AIMessage.id).all()
    return {"id":conv.id,"user_id":conv.user_id,"title":conv.title,"messages":[{"id":m.id,"role":m.role,"content":m.content} for m in msgs]}

# ---------- Reports ----------
def report_data(db, user_id, year, month=None):
    s=compute_summary(db, user_id, year, month)
    cats=category_breakdown(db, user_id, year, month)
    return {**s, "year": year, "month": month, "category_breakdown": cats, "spending_breakdown": cats,
            "budget_performance": [budget_out(db,b) for b in db.query(Budget).filter(Budget.user_id==user_id).all() if (month is None or b.month==month) and b.year==year]}

@router.get("/reports/monthly")
def monthly_report(year: int = Query(default=None), month: int = Query(default=None), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    today=date.today(); y=year or today.year; m=month or today.month
    return report_data(db, current.id, y, m)
@router.get("/reports/yearly")
def yearly_report(year: int = Query(default=None), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    today=date.today(); y=year or today.year
    return report_data(db, current.id, y, None)
@router.get("/reports/export")
def export_report(format: str = "csv", year: int = None, month: int = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    today=date.today(); y=year or today.year
    data_r=report_data(db, current.id, y, month)
    if format.lower()=="pdf":
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        buf=io.BytesIO(); c=canvas.Canvas(buf, pagesize=A4)
        c.drawString(50,800,"FinSight AI Financial Report"); ypos=770
        for k in ("total_income","total_expense","net_balance","savings_rate"):
            c.drawString(50,ypos,f"{k}: {data_r[k]}"); ypos-=20
        for cat in data_r["category_breakdown"]:
            c.drawString(50,ypos,f"{cat['category']}: {cat['total']}"); ypos-=18
            if ypos<50: c.showPage(); ypos=800
        c.save(); buf.seek(0)
        return Response(content=buf.read(), media_type="application/pdf", headers={"Content-Disposition":"attachment; filename=report.pdf"})
    buf=io.StringIO(); w=csv.writer(buf); w.writerow(["metric","value"]); 
    for k in ("total_income","total_expense","net_balance","savings_rate"): w.writerow([k,data_r[k]])
    w.writerow(["category","total"])
    for cat in data_r["category_breakdown"]: w.writerow([cat["category"],cat["total"]])
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=report.csv"})
@router.get("/reports/monthly/export")
def monthly_export(format: str = "csv", year: int = None, month: int = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return export_report(format, year, month, db, current)

@router.get("/reports/yearly/export")
def yearly_export(format: str = "csv", year: int = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return export_report(format, year, None, db, current)


# ---------- Advanced: cashflow & affordability ----------
@router.get("/ml/cashflow")
def get_cashflow(horizon_days: int = 30, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return cashflow_projection(db, current.id, horizon_days=horizon_days)

@router.post("/simulator/trajectory")
def post_trajectory(data: TrajectoryIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.analytics.advanced import scenario_trajectory
    return scenario_trajectory(db, current.id, category_name=data.category_name,
                               reduction_percent=data.reduction_percent,
                               extra_monthly_savings=data.extra_monthly_savings,
                               income_change_percent=data.income_change_percent,
                               one_off_expense=data.one_off_expense, months=data.months)

@router.get("/goals/{gid}/forecast")
def get_goal_forecast(gid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    from app.analytics.advanced import goal_forecast
    g = db.query(FinancialGoal).filter(FinancialGoal.id == gid, FinancialGoal.user_id == current.id).first()
    if not g:
        raise HTTPException(404, "Goal not found")
    return goal_forecast(db, current.id, g)

@router.delete("/goals/{gid}")
def delete_goal(gid: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    g = db.query(FinancialGoal).filter(FinancialGoal.id == gid, FinancialGoal.user_id == current.id).first()
    if not g:
        raise HTTPException(404, "Goal not found")
    db.delete(g); db.commit()
    return {"removed": True, "id": gid}

@router.post("/simulator/afford")
def post_afford(data: AffordIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return affordability(db, current.id, data.item_name, data.cost, data.months)
