import numpy as np
from collections import defaultdict, Counter
from sqlalchemy.orm import Session
from app.models.models import Transaction, AnomalyAlert
from app.agents.sanitize import sanitize_text

def detect_anomalies(db: Session, user_id: int, persist: bool = True):
    txns=db.query(Transaction).filter(Transaction.user_id==user_id).order_by(Transaction.date).all()
    expenses=[t for t in txns if t.type=="expense"]
    anomalies=[]
    def add(t, reason, score, sev, typ):
        anomalies.append({"transaction_id":t.id if t else None,"reason":reason,"score":round(float(score),4),"severity":sev,"anomaly_type":typ,"type":typ,"confidence":round(float(min(abs(score),1.0)),4) if typ!="duplicate" else 0.95,"merchant":sanitize_text(t.merchant) if t else "","amount":float(t.amount) if t else 0,"category_name":t.category_name if t else ""})
    if not expenses:
        return anomalies
    amounts=np.array([float(t.amount) for t in expenses])
    median=np.median(amounts); mad=np.median(np.abs(amounts-median)) or 1.0
    # robust z + isolation forest scores
    iso_scores={}
    if len(expenses)>=20:
        try:
            from sklearn.ensemble import IsolationForest
            X=amounts.reshape(-1,1)
            clf=IsolationForest(contamination=0.1, random_state=42)
            clf.fit(X)
            scores=clf.decision_function(X)  # lower = more anomalous
            preds=clf.predict(X)
            for i,t in enumerate(expenses):
                if preds[i]==-1:
                    iso_scores[t.id]=float(-scores[i])
        except Exception:
            pass
    seen={}
    merchant_counts=Counter([t.merchant for t in expenses if t.merchant])
    # category totals for spike: monthly per category
    cat_month=defaultdict(list)
    for t in expenses:
        cat_month[(t.category_name, t.date.strftime("%Y-%m"))].append(float(t.amount))
    cat_avg={}
    for (cat,mon), vals in cat_month.items():
        cat_avg.setdefault(cat, []).append(sum(vals))
    for t in expenses:
        amt=float(t.amount)
        rz=0.6745*(amt-median)/mad if mad else 0
        if abs(rz)>3.5 and amt>median:
            add(t, f"Unusual transaction amount ₹{amt:.2f} compared to typical spending (median ₹{median:.2f}, robust z-score {rz:.2f}). This is a statistical observation, not a fraud claim.", abs(rz)/10, "high" if abs(rz)>5 else "medium", "unusual_amount")
        elif t.id in iso_scores:
            add(t, f"Isolation Forest flagged amount ₹{amt:.2f} as statistically unusual for this user. This is not a fraud claim.", iso_scores[t.id], "medium", "isolation_forest")
        # duplicate
        key=(amt, (t.merchant or "").lower(), t.date.isoformat(), (t.description or "").lower())
        if key in seen:
            add(t, f"Possible duplicate transaction: same amount, merchant and date as transaction {seen[key]}.", 0.9, "medium", "duplicate")
        else:
            seen[key]=t.id
        # unusual merchant: first occurrence and large
        if t.merchant and merchant_counts[t.merchant]==1 and amt>median*2 and len(expenses)>=10:
            # only if not already added for this txn unusual_amount? allow separate but avoid dup in tests: add if rz not high
            if abs(rz)<=3.5:
                add(t, f"First transaction with merchant '{sanitize_text(t.merchant)}' and amount ₹{amt:.2f} above typical spending. Not a fraud claim.", 0.6, "low", "unusual_merchant")
    # category spikes as transaction-level? Add spike anomalies for largest txn in spiking month
    for cat, monthly_vals in cat_avg.items():
        if len(monthly_vals)>=2:
            avg=np.mean(monthly_vals[:-1]) if len(monthly_vals)>1 else monthly_vals[0]
            last=monthly_vals[-1]
            if avg>0 and last>avg*1.8:
                candidates=[t for t in expenses if t.category_name==cat]
                if candidates:
                    t=max(candidates, key=lambda x: float(x.amount))
                    # avoid duplicate anomaly for same txn/type
                    if not any(a["transaction_id"]==t.id and a["anomaly_type"]=="category_spike" for a in anomalies):
                        add(t, f"Category '{cat}' spending spiked to ₹{last:.2f} vs average ₹{avg:.2f}.", 0.8, "medium", "category_spike")
    if persist and anomalies:
        # clear old open? Keep simple: delete previous open to avoid duplication in tests repeated calls? Instead check existing by txn+type
        existing={(a.transaction_id,a.anomaly_type) for a in db.query(AnomalyAlert).filter(AnomalyAlert.user_id==user_id).all()}
        for a in anomalies:
            if (a["transaction_id"], a["anomaly_type"]) in existing:
                continue
            db.add(AnomalyAlert(user_id=user_id, transaction_id=a["transaction_id"], severity=a["severity"], reason=a["reason"], score=a["score"], anomaly_type=a["anomaly_type"]))
        db.commit()
    return anomalies
