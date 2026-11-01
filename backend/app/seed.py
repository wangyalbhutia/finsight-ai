"""Seed demo user demo@finsight.ai / Demo@1234 with ~180 days synthetic txns. Dev/demo only."""
import random, hashlib
from datetime import date, timedelta
from decimal import Decimal
from app.core.database import SessionLocal, Base, engine
from app.models.models import User, Transaction, Budget, Category
from app.core.security import hash_password

def dedup(user_id, d, amt, merch, desc, typ):
    return hashlib.sha256(f"{user_id}|{d}|{amt}|{merch.lower()}|{desc.lower()}|{typ}".encode()).hexdigest()

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal(); random.seed(42)
    user = db.query(User).filter(User.email=="demo@finsight.ai").first()
    if not user:
        user = User(email="demo@finsight.ai", full_name="Demo User", hashed_password=hash_password("Demo@1234"), currency="INR", preferred_currency="INR")
        db.add(user); db.commit(); db.refresh(user)
    if db.query(Transaction).filter(Transaction.user_id==user.id).count() > 10:
        print(f"Already seeded user {user.id}"); db.close(); return user
    cats = [("Swiggy","Food & Dining",300,900),("BigBasket","Groceries",500,2000),("Uber","Transport",150,600),("Amazon","Shopping",500,3000),("Netflix","Entertainment",199,649),("Airtel","Utilities",299,999),("Apollo Pharmacy","Healthcare",200,1200),("Udemy","Education",499,1499)]
    start = date.today() - timedelta(days=180)
    for day in range(180):
        d = start + timedelta(days=day)
        if day % 30 == 0:
            amt = Decimal("60000")
            db.add(Transaction(user_id=user.id, type="income", amount=amt, currency="INR", category_name="Salary", merchant="Employer", description="monthly salary payroll", date=d, dedup_hash=dedup(user.id,d,amt,"Employer","monthly salary payroll","income")))
        if day % 30 == 1:
            amt = Decimal("15000")
            db.add(Transaction(user_id=user.id, type="expense", amount=amt, currency="INR", category_name="Rent", merchant="Landlord", description="house rent landlord", date=d, is_recurring=True, dedup_hash=dedup(user.id,d,amt,"Landlord","house rent landlord","expense")))
        for merch, cat, lo, hi in cats:
            if random.random() < 0.28:
                amt = Decimal(str(round(random.uniform(lo,hi),2)))
                desc = f"{merch} payment"
                db.add(Transaction(user_id=user.id, type="expense", amount=amt, currency="INR", category_name=cat, merchant=merch, description=desc, date=d, is_recurring=merch in ("Netflix","Airtel"), dedup_hash=dedup(user.id,d,amt,merch,desc,"expense")))
    db.add(Budget(user_id=user.id, category_name="Overall", amount=Decimal("40000"), month=date.today().month, year=date.today().year))
    for name in ["Food & Dining","Groceries","Transport","Shopping","Entertainment","Utilities","Healthcare","Education","Rent","Salary"]:
        db.add(Category(user_id=user.id, name=name, type="expense"))
    db.commit(); print(f"Seeded demo user {user.id} with {db.query(Transaction).filter(Transaction.user_id==user.id).count()} txns"); db.close(); return user

if __name__ == "__main__":
    seed()
