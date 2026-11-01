from app.agents import analytics_agent, prediction_agent, anomaly_agent, recommendation_agent
from app.integrations.llm import llm
from app.analytics.service import category_breakdown, compute_summary
from app.analytics.advanced import financial_health_score, smart_insights, detect_subscriptions, affordability
from app.intelligence.engine import get_engine
import re

def simulate(db, user_id, category_name, reduction_percent):
    # Clamp defensively: callers include free-text chat parsing, where a
    # percentage above 100 would otherwise produce negative "proposed" spending.
    reduction_percent = min(max(float(reduction_percent), 0.0), 100.0)
    cats=category_breakdown(db,user_id)
    current=sum(c['total'] for c in cats if c['category'].lower()==category_name.lower())
    if current==0:
        # try partial match
        current=sum(c['total'] for c in cats if category_name.lower() in c['category'].lower())
    proposed=current*(1-reduction_percent/100)
    monthly_saving=current-proposed
    return {"category_name":category_name,"reduction_percent":reduction_percent,"current_spending":round(current,2),"current":round(current,2),"proposed_spending":round(proposed,2),"proposed":round(proposed,2),"monthly_savings":round(monthly_saving,2),"savings":round(monthly_saving,2),"monthly_impact":round(monthly_saving,2),"annual_savings":round(monthly_saving*12,2),"annualised_impact":round(monthly_saving*12,2),"annual_impact":round(monthly_saving*12,2)}

def route(db, user_id, message: str):
    m=message.lower()
    engine=get_engine(db, user_id)  # single analytical source for this request
    # --- advanced intents (deterministic tools; LLM never invents numbers) ---
    if any(k in m for k in ["health score", "financial health", "how healthy"]):
        hs=engine.health_score()
        if hs.get("insufficient_data"):
            text="I can't compute a health score yet — add some transactions first and I'll score your savings rate, budgets, stability, anomalies and buffer."
            return {"agent":"health","health_score":hs,"text":text,"response":text,"tools_used":["financial_health_score"]}
        weakest=hs["components"][hs["weakest_component"]]
        text=(f"Your financial health score is {hs['score']}/100 (grade {hs['grade']}). "
              f"Savings rate component: {hs['components']['savings_rate']['score']}/100, budget adherence: {hs['components']['budget_adherence']['score']}/100, "
              f"spending stability: {hs['components']['spending_stability']['score']}/100. Weakest area: {hs['weakest_component'].replace('_',' ')} — {weakest['note']}")
        return {"agent":"health","health_score":hs,"text":text,"response":text,"tools_used":["financial_health_score"]}
    if "subscription" in m:
        subs=engine.subscriptions()
        if not subs["count"]:
            text="I couldn't detect any subscriptions from your charge patterns yet. Subscriptions appear once the same merchant has charged you at least 3 times at a regular interval with a stable amount."
            return {"agent":"subscriptions","subscriptions":subs,"text":text,"response":text,"tools_used":["subscription_detection"]}
        top=", ".join(f"{s['merchant']} ₹{s['monthly_cost']:,.2f}/mo" for s in subs["subscriptions"][:3])
        text=(f"You have {subs['count']} detected subscription(s) costing ₹{subs['total_monthly_cost']:,.2f} per month "
              f"(₹{subs['total_annual_cost']:,.2f} per year). Largest: {top}.")
        return {"agent":"subscriptions","subscriptions":subs,"text":text,"response":text,"tools_used":["subscription_detection"]}
    if "afford" in m or "can i buy" in m:
        amt_match=re.search(r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b|thousand|lakh|lakhs)?", m)
        months_match=re.search(r"(\d+)\s*month", m)
        if amt_match:
            amt=float(amt_match.group(1).replace(",", "")) * (1000 if amt_match.group(2)=="k" or (amt_match.group(2) and amt_match.group(2).startswith("thousand")) else 100000 if amt_match.group(2) and amt_match.group(2).startswith("lakh") else 1)
            months=int(months_match.group(1)) if months_match else 6
            aff=engine.affordability("this purchase", amt, months)
            if aff["months_needed_at_current_surplus"] is None:
                text=(f"Based on your last 3 months, your average monthly surplus is ₹{aff['average_monthly_surplus']:,.2f}, so saving for a ₹{amt:,.2f} purchase isn't currently feasible — expenses are at or above income. "
                      f"You'd need ₹{aff['required_monthly_saving']:,.2f}/month for {months} months.")
            else:
                text=(f"For a ₹{amt:,.2f} purchase: your average monthly surplus is ₹{aff['average_monthly_surplus']:,.2f}. "
                      f"Over {months} months you'd need to save ₹{aff['required_monthly_saving']:,.2f}/month — {'feasible at your current surplus' if aff['feasible_within_requested_months'] else 'not quite feasible in that window'}. "
                      f"At your current surplus alone it would take about {aff['months_needed_at_current_surplus']} month(s), reaching it around {aff['projected_affordable_date']}.")
            return {"agent":"affordability","affordability":aff,"text":text,"response":text,"tools_used":["affordability_planner"]}
        text="Tell me the price and I'll check it against your average monthly surplus — for example: 'Can I afford a phone for ₹60,000 in 6 months?'"
        return {"agent":"affordability","text":text,"response":text,"tools_used":["affordability_planner"]}
    if "insight" in m:
        ins=engine.insights()
        if ins.get("insufficient_data") or not ins["insights"]:
            text="I don't have enough transaction data yet to generate insights. Add or import transactions and ask again."
            return {"agent":"insights","insights":ins,"text":text,"response":text,"tools_used":["smart_insights"]}
        text="Here are your top insights: " + " ".join(f"({i+1}) {x['title']} — {x['detail']}" for i, x in enumerate(ins["insights"][:3]))
        return {"agent":"insights","insights":ins,"text":text,"response":text,"tools_used":["smart_insights"]}
    # what-if simulation inside chat
    if "reduce" in m or "what if" in m or "simulate" in m:
        # try extract percent and category guess
        pct_match=re.search(r"(\d+(?:\.\d+)?)\s*%", message)
        pct=float(pct_match.group(1)) if pct_match else 10.0
        cats=category_breakdown(db,user_id)
        cat_name=cats[0]['category'] if cats else "Food & Dining"
        for c in cats:
            if c['category'].lower() in m or any(w in m for w in c['category'].lower().split()):
                cat_name=c['category']; break
        if "food" in m: 
            for c in cats:
                if "food" in c['category'].lower(): cat_name=c['category']
        sim=simulate(db,user_id,cat_name,pct)
        text=f"If you reduce {cat_name} by {pct:.0f}%: current ₹{sim['current_spending']:.2f}, proposed ₹{sim['proposed_spending']:.2f}, monthly savings ₹{sim['monthly_savings']:.2f}, annualised savings ₹{sim['annual_savings']:.2f}."
        return {"agent":"recommendation","simulation":sim,"text":text,"response":text,"tools_used":["simulator","analytics"]}
    if any(k in m for k in ["predict","forecast","next month","exceed my budget","overrun","will i exceed"]):
        # budget exceed also needs prediction; prediction agent covers, but check budgets in endpoint layer
        result=prediction_agent.run(db,user_id,message); result["tools_used"]=["forecasting"]; return result
    if any(k in m for k in ["unusual","anomal","strange","duplicate"]):
        result=anomaly_agent.run(db,user_id,message); result["tools_used"]=["anomaly_detection"]; return result
    if any(k in m for k in ["suggest","save","savings","improve","recommend","how can i"]):
        result=recommendation_agent.run(db,user_id,message); result["tools_used"]=["analytics","recommendation"]; return result
    # default analytics (covers condition, increase, category, compare, most money)
    result=analytics_agent.run(db,user_id,message); result["tools_used"]=["analytics"]
    # Use LLM adapter to polish but fallback keeps grounded numbers
    result["text"]=llm.complete(f"Explain only these facts, do not invent numbers: {result['text']}", fallback=result["text"])
    result["response"]=result["text"]
    return result
