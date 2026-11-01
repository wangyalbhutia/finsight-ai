import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

TRAIN = [
    ("swiggy food delivery order", "Food & Dining"), ("zomato restaurant dinner", "Food & Dining"), ("dominos pizza", "Food & Dining"), ("mcdonalds burger meal", "Food & Dining"), ("cafe coffee day", "Food & Dining"), ("restaurant lunch bill", "Food & Dining"),
    ("bigbasket groceries vegetables", "Groceries"), ("blinkit milk bread groceries", "Groceries"), ("dmart supermarket grocery", "Groceries"), ("fresh fruits vegetables market", "Groceries"),
    ("uber cab ride", "Transport"), ("ola taxi trip", "Transport"), ("petrol fuel station", "Transport"), ("indian railways train ticket", "Transport"), ("metro card recharge transport", "Transport"), ("flight ticket indigo airlines", "Transport"),
    ("amazon shopping headphones", "Shopping"), ("flipkart online shopping shoes", "Shopping"), ("myntra clothing fashion", "Shopping"), ("zara clothes shopping", "Shopping"),
    ("netflix subscription", "Entertainment"), ("spotify premium music", "Entertainment"), ("bookmyshow movie ticket", "Entertainment"), ("prime video subscription", "Entertainment"),
    ("electricity bill payment", "Utilities"), ("water bill utilities", "Utilities"), ("jio mobile recharge", "Utilities"), ("airtel broadband internet bill", "Utilities"), ("gas cylinder bill", "Utilities"),
    ("apollo pharmacy medicine", "Healthcare"), ("hospital doctor consultation", "Healthcare"), ("medical lab test health", "Healthcare"), ("pharmacy tablets", "Healthcare"),
    ("udemy online course", "Education"), ("coursera course fees", "Education"), ("school tuition fees education", "Education"), ("books stationery study", "Education"),
    ("house rent landlord", "Rent"), ("monthly rent apartment", "Rent"), ("hostel rent payment", "Rent"),
    ("salary credit employer", "Salary"), ("monthly salary payroll", "Salary"), ("freelance payment income", "Salary"),
    ("gym membership fitness", "Healthcare"), ("cult fit gym", "Healthcare"),
    ("salon haircut grooming", "Shopping"),
]

RULES = [
    (r"swiggy|zomato|dominos|pizza|restaurant|cafe|mcdonald", "Food & Dining"),
    (r"bigbasket|blinkit|dmart|grocery|groceries", "Groceries"),
    (r"uber|ola|petrol|fuel|railway|metro|indigo", "Transport"),
    (r"amazon|flipkart|myntra|zara", "Shopping"),
    (r"netflix|spotify|bookmyshow|prime video", "Entertainment"),
    (r"electricity|water bill|jio|airtel|broadband", "Utilities"),
    (r"pharmacy|apollo|hospital|doctor", "Healthcare"),
    (r"udemy|coursera|tuition|course", "Education"),
    (r"rent|landlord", "Rent"),
    (r"salary|payroll", "Salary"),
]

def preprocess(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()

class Categorizer:
    def __init__(self):
        texts = [preprocess(t) for t,_ in TRAIN]
        labels = [l for _,l in TRAIN]
        self.vectorizer = TfidfVectorizer()
        X = self.vectorizer.fit_transform(texts)
        self.clf = LogisticRegression(max_iter=1000)
        self.clf.fit(X, labels)
    def predict(self, description: str = "", merchant: str = ""):
        combined = preprocess(f"{merchant} {description}")
        # rule fallback first for known merchants (high precision)
        for pat, cat in RULES:
            if re.search(pat, combined):
                return {"category": cat, "category_name": cat, "confidence": 0.95, "method": "rule"}
        if not combined:
            return {"category": "Uncategorized", "category_name": "Uncategorized", "confidence": 0.0, "method": "fallback"}
        X = self.vectorizer.transform([combined])
        proba = self.clf.predict_proba(X)[0]
        idx = proba.argmax()
        return {"category": str(self.clf.classes_[idx]), "category_name": str(self.clf.classes_[idx]), "confidence": round(float(proba[idx]),4), "method": "ml"}

_categorizer = None
def get_categorizer():
    global _categorizer
    if _categorizer is None:
        _categorizer = Categorizer()
    return _categorizer

def suggest_category(description: str = "", merchant: str = ""):
    return get_categorizer().predict(description, merchant)
