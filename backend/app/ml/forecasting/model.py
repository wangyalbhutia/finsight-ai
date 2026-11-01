import numpy as np, pandas as pd
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.models.models import Transaction, Prediction

MODEL_VERSION = "exp_smoothing_v1"
MIN_DAYS = 7  # sparse history threshold

def _daily_series(db, user_id, category_name=None):
    # Stage 2: daily sums are aggregated in SQL (one row per day) instead of
    # loading every expense transaction into Python.
    from sqlalchemy import func
    q = db.query(Transaction.date, func.sum(Transaction.amount)).filter(
        Transaction.user_id==user_id, Transaction.type=="expense")
    if category_name:
        q = q.filter(Transaction.category_name==category_name)
    rows = q.group_by(Transaction.date).order_by(Transaction.date).all()
    if not rows:
        return pd.Series(dtype=float)
    data={d: float(total or 0) for d, total in rows}
    idx=pd.date_range(start=min(data.keys()), end=max(data.keys()), freq="D")
    return pd.Series([data.get(d.date(),0.0) for d in idx], index=idx)

def chronological_split(series, ratio=0.8):
    """Explicit chronological split — NO shuffling. Returns train, test, and date bounds for verification."""
    split=int(len(series)*ratio)
    train=series.iloc[:split]; test=series.iloc[split:]
    info={
        "train_start": train.index[0].isoformat() if len(train) else None,
        "train_end": train.index[-1].isoformat() if len(train) else None,
        "test_start": test.index[0].isoformat() if len(test) else None,
        "test_end": test.index[-1].isoformat() if len(test) else None,
        "max_train_date": train.index[-1].isoformat() if len(train) else None,
        "min_test_date": test.index[0].isoformat() if len(test) else None,
        "is_chronological": (len(train)==0 or len(test)==0 or train.index[-1] < test.index[0]),
        "shuffled": False,
    }
    return train, test, info

def _metrics(y_true, y_pred):
    y_true=np.array(y_true,dtype=float); y_pred=np.array(y_pred,dtype=float)
    if len(y_true)==0: return {"mae":0.0,"rmse":0.0,"mape":None}
    mae=float(np.mean(np.abs(y_true-y_pred))); rmse=float(np.sqrt(np.mean((y_true-y_pred)**2)))
    mask=y_true!=0
    mape=float(np.mean(np.abs((y_true[mask]-y_pred[mask])/y_true[mask]))*100) if mask.any() else None
    return {"mae":round(mae,2),"rmse":round(rmse,2),"mape":round(mape,2) if mape is not None else None}

def evaluate_models(series):
    """Compare models vs naive baselines on chronological hold-out."""
    if len(series) < 14:
        return {"insufficient_data": len(series) < MIN_DAYS, "split": chronological_split(series)[2] if len(series) else {}, "models": {}}
    train, test, info = chronological_split(series)
    results={}
    # naive last-value
    results["naive_last_value"]=_metrics(test.values, np.array([train.iloc[-1]]*len(test)))
    # moving average baseline
    ma=train.tail(7).mean()
    results["moving_average"]=_metrics(test.values, np.array([ma]*len(test)))
    # exponential smoothing
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        m=ExponentialSmoothing(train, trend="add", seasonal=None).fit(optimized=True)
        results["exponential_smoothing"]=_metrics(test.values, np.array(m.forecast(len(test)),dtype=float))
    except Exception as e:
        results["exponential_smoothing"]=_metrics(test.values, np.array([ma]*len(test)))
    return {"insufficient_data": False, "split": info, "models": results}

def backtest(series):
    ev=evaluate_models(series)
    if not ev["models"]:
        if len(series)==0: return {"mae":0.0,"rmse":0.0,"mape":None,"method":"moving_average","split":ev.get("split",{})}
        pred=[series.mean()]*len(series); mm=_metrics(series.values,pred); mm["method"]="moving_average"; mm["split"]=ev.get("split",{}); return mm
    # primary method = exponential_smoothing if present
    primary=ev["models"].get("exponential_smoothing", ev["models"]["moving_average"])
    return {**primary, "method":"exponential_smoothing", "split":ev["split"], "models":ev["models"]}

def forecast(db: Session, user_id: int, horizon_days: int = 30, category_name: str = None):
    series=_daily_series(db,user_id,category_name)
    if len(series) < MIN_DAYS:
        # Honest insufficient-data response — NO fabricated forecast, NO persisted Prediction, NO interval
        return {"horizon_days":horizon_days,"predicted_amount":None,"total_predicted":None,"daily_average":None,
                "lower_bound":None,"upper_bound":None,"prediction_interval":None,"prediction_interval_supported":False,
                "model_version":MODEL_VERSION,"method":None,"metrics":{"mae":None,"rmse":None,"mape":None},
                "mae":None,"rmse":None,"mape":None,"forecast_points":[],"points":[],
                "category_name":category_name or "Overall","insufficient_data":True,
                "message":f"Insufficient data: need at least {MIN_DAYS} days of expense history, have {len(series)} day(s). No forecast fabricated."}
    metrics=backtest(series)
    try:
        if len(series)>=14:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            model=ExponentialSmoothing(series, trend="add", seasonal=None).fit(optimized=True)
            preds=np.array(model.forecast(horizon_days),dtype=float); method="exponential_smoothing"; interval_supported=True
        else:
            raise ValueError("short series: use moving average, interval is empirical not model-based")
    except Exception:
        ma_val=series.tail(min(7,len(series))).mean(); preds=np.array([ma_val]*horizon_days,dtype=float); method="moving_average"; interval_supported=False
    preds=np.maximum(preds,0)
    std=float(series.std()) if len(series)>1 else 0.0
    total=float(preds.sum())
    if interval_supported:
        lower=max(0.0,total-1.96*std*np.sqrt(horizon_days)); upper=total+1.96*std*np.sqrt(horizon_days)
        interval=[round(lower,2),round(upper,2)]
    else:
        lower=upper=None; interval=None
    start=series.index[-1].date()+timedelta(days=1)
    points=[{"date":(start+timedelta(days=i)).isoformat(),"predicted":round(float(preds[i]),2)} for i in range(len(preds))]
    result={"horizon_days":horizon_days,"predicted_amount":round(total,2),"total_predicted":round(total,2),
            "daily_average":round(total/horizon_days,2) if horizon_days else 0,
            "lower_bound":round(lower,2) if lower is not None else None,"upper_bound":round(upper,2) if upper is not None else None,
            "prediction_interval":interval,"prediction_interval_supported":interval_supported,
            "prediction_interval_note":"Model-based approx interval (exp smoothing, ±1.96σ)" if interval_supported else "Not provided: moving-average fallback does not support a model prediction interval",
            "model_version":MODEL_VERSION,"method":method,"metrics":metrics,"mae":metrics["mae"],"rmse":metrics["rmse"],"mape":metrics["mape"],
            "forecast_points":points,"points":points,"category_name":category_name or "Overall","insufficient_data":False}
    try:
        db.add(Prediction(user_id=user_id,horizon_days=horizon_days,predicted_amount=total,lower_bound=lower,upper_bound=upper,category_name=category_name or "Overall",model_version=MODEL_VERSION,mae=metrics["mae"],rmse=metrics["rmse"],mape=metrics["mape"])); db.commit()
    except Exception:
        db.rollback()
    return result

def forecast_all(db: Session, user_id: int):
    f7=forecast(db,user_id,7); f30=forecast(db,user_id,30)
    today=date.today(); import calendar; last=calendar.monthrange(today.year,today.month)[1]; remaining=max(1,last-today.day)
    fmonth=forecast(db,user_id,remaining)
    cats=db.query(Transaction.category_name).filter(Transaction.user_id==user_id,Transaction.type=="expense").distinct().all()
    cat_forecasts=[]
    for (c,) in cats:
        if c:
            cf=forecast(db,user_id,30,category_name=c)
            cat_forecasts.append({"category":c,"category_name":c,"predicted_amount":cf["predicted_amount"],"insufficient_data":cf["insufficient_data"]})
    series=_daily_series(db,user_id)
    evaluation=evaluate_models(series) if len(series)>=14 else {"insufficient_data":True,"models":{},"split":chronological_split(series)[2] if len(series) else {}}
    return {"next_7_days":f7,"next_30_days":f30,"month_end":fmonth,"end_of_month":fmonth,
            "expected_monthly_expenditure":f30["predicted_amount"],"category_wise":cat_forecasts,"category_forecasts":cat_forecasts,
            "metrics":f30["metrics"],"model_version":MODEL_VERSION,"evaluation":evaluation,"insufficient_data":f30["insufficient_data"]}


def _model_predictions(train, horizon):
    """One-step-ahead-style flat forecasts per model for a train window."""
    preds = {"naive_last_value": np.array([float(train.iloc[-1])] * horizon),
             "moving_average": np.array([float(train.tail(7).mean())] * horizon)}
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        m = ExponentialSmoothing(train, trend="add", seasonal=None).fit(optimized=True)
        preds["exponential_smoothing"] = np.array(m.forecast(horizon), dtype=float)
    except Exception:
        preds["exponential_smoothing"] = preds["moving_average"]
    return preds


def rolling_origin_evaluation(series, min_train=14, horizon=7):
    """Stage 6 (Feature D): evaluate at several chronological origins and
    average — a single hold-out split can flatter a model by luck. Origins
    are strictly chronological; no future data ever enters a train window."""
    n = len(series)
    if n < min_train + horizon:
        return {"insufficient_data": True, "origins": 0, "models": {}, "best_model": None}
    cuts = sorted({int(n * f) for f in (0.55, 0.7, 0.85)
                   if min_train <= int(n * f) <= n - horizon})
    if not cuts:
        return {"insufficient_data": True, "origins": 0, "models": {}, "best_model": None}
    collected = {}
    for cut in cuts:
        train, test = series.iloc[:cut], series.iloc[cut:cut + horizon]
        for name, pred in _model_predictions(train, len(test)).items():
            mm = _metrics(test.values, pred)
            collected.setdefault(name, []).append(mm)
    models = {}
    for name, runs in collected.items():
        models[name] = {"mae": round(float(np.mean([r["mae"] for r in runs])), 2),
                        "rmse": round(float(np.mean([r["rmse"] for r in runs])), 2),
                        "origins": len(runs)}
    best = min(models.items(), key=lambda kv: kv[1]["mae"])[0] if models else None
    return {"insufficient_data": False, "origins": len(cuts), "models": models,
            "best_model": best, "method": "rolling_origin_chronological"}


def category_evaluations(db, user_id):
    """Stage 6 (Feature D): per-category model evaluation. Each category's
    daily series is evaluated independently; categories with too little
    history are reported as insufficient rather than scored with noise."""
    from sqlalchemy import distinct
    from app.models.models import Transaction
    cats = [r[0] for r in db.query(distinct(Transaction.category_name)).filter(
        Transaction.user_id == user_id, Transaction.type == "expense").all() if r[0]]
    out = []
    for cat in cats:
        series = _daily_series(db, user_id, cat)
        if len(series) < 21:
            out.append({"category": cat, "days": int(len(series)), "insufficient_data": True})
            continue
        ev = evaluate_models(series)
        ro = rolling_origin_evaluation(series)
        out.append({"category": cat, "days": int(len(series)), "insufficient_data": False,
                    "holdout_models": ev.get("models", {}),
                    "rolling_origin": ro,
                    "best_model": ro.get("best_model")})
    out.sort(key=lambda x: -x["days"])
    return out
