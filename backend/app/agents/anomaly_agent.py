from app.ml.anomaly_detection.model import detect_anomalies
def run(db, user_id, message=""):
    anomalies=detect_anomalies(db,user_id,persist=True)
    if not anomalies:
        text="No unusual spending patterns were detected in your transactions."
    else:
        text=f"Found {len(anomalies)} unusual transaction(s). " + " ".join([a['reason'] for a in anomalies[:3]])
    return {"agent":"anomaly","anomalies":anomalies,"text":text,"response":text}
