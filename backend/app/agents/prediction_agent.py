from app.ml.forecasting.model import forecast_all, forecast
def run(db, user_id, message=""):
    f=forecast_all(db,user_id)
    text=f"Forecast: next 7 days ₹{f['next_7_days']['predicted_amount']:.2f}, next 30 days ₹{f['next_30_days']['predicted_amount']:.2f} (model {f['model_version']}, MAE ₹{f['next_30_days']['metrics']['mae']:.2f}, RMSE ₹{f['next_30_days']['metrics']['rmse']:.2f}). Expected monthly expenditure ₹{f['expected_monthly_expenditure']:.2f}."
    return {"agent":"prediction","forecast":f,"text":text,"response":text}
