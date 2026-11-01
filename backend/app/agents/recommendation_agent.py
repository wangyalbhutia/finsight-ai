from app.intelligence.engine import get_engine
def recommendations(db, user_id):
    _e=get_engine(db,user_id); s=_e.summary(); cats=_e.category_breakdown()
    recs=[]
    if s['savings_rate']<20 and s['total_income']>0:
        recs.append(f"Your savings rate is {s['savings_rate']:.2f}%, below the 20% guideline. Consider reducing discretionary spending.")
    for c in cats[:3]:
        if s['total_expense']>0 and c['total']/s['total_expense']>0.3:
            saving=c['total']*0.1
            recs.append(f"{c['category']} is {c['total']/s['total_expense']*100:.1f}% of expenses (₹{c['total']:.2f}). A 10% reduction would save ₹{saving:.2f}.")
    if not recs:
        recs.append("Your spending is well distributed. Keep tracking and maintain an emergency fund.")
    return recs

def run(db, user_id, message=""):
    # simulator intent handled here if 'reduce' / 'simulate' / 'what if'
    recs=recommendations(db,user_id)
    text="Recommendations: " + " ".join(recs)
    return {"agent":"recommendation","recommendations":recs,"text":text,"response":text}
