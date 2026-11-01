from app.intelligence.engine import get_engine
def run(db, user_id, message=""):
    engine = get_engine(db, user_id)
    s = engine.summary()
    cats = engine.category_breakdown()
    top = cats[0] if cats else None
    text = f"Your finances: total income ₹{s['total_income']:.2f}, total expenses ₹{s['total_expense']:.2f}, net balance ₹{s['net_balance']:.2f}, savings rate {s['savings_rate']:.2f}%."
    if top:
        text += f" Your highest spending category is {top['category']} at ₹{top['total']:.2f}."
    if "increase" in message.lower() or "why" in message.lower():
        tr = engine.trends()["monthly"]
        if len(tr) >= 2:
            parts = ", ".join([c['category'] + " Rs" + format(c['total'], ".2f") for c in cats[:3]])
            text += f" Monthly spending changed from ₹{tr[-2]['total']:.2f} ({tr[-2]['month']}) to ₹{tr[-1]['total']:.2f} ({tr[-1]['month']}). Top categories: {parts}."
    if "compare" in message.lower():
        tr = engine.trends()["monthly"][-3:]
        text += " Last months: " + ", ".join([f"{m['month']}: ₹{m['total']:.2f}" for m in tr]) + "."
    return {"agent": "analytics", "summary": s, "categories": cats, "text": text, "response": text}
