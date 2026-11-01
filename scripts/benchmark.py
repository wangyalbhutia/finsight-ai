#!/usr/bin/env python3
"""FinSight AI performance benchmark (Stage 2 acceptance).

Builds a deterministic synthetic dataset (seed 7) at 1k / 10k / 49k
transactions and measures, per size: summary, composite dashboard,
smart insights, and the 30-day forecast — wall time, SQL query count
(SQLAlchemy event listener), and Python memory (tracemalloc peak for the
dashboard call). Usage:

    backend/.venv/bin/python scripts/benchmark.py benchmarks/before.json
"""
import json
import os
import random
import sys
import time
import tracemalloc
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ["DATABASE_URL"] = "sqlite:////tmp/finsight_bench.db"
if os.path.exists("/tmp/finsight_bench.db"):
    os.remove("/tmp/finsight_bench.db")

from sqlalchemy import event  # noqa: E402
from app.models import models  # noqa: E402,F401
from app.core.database import Base, engine, SessionLocal  # noqa: E402
from app.models.models import User, Transaction  # noqa: E402
from app.core.security import hash_password_safe  # noqa: E402

Base.metadata.create_all(bind=engine)
db = SessionLocal()
u = User(email="b@b.ai", full_name="B", hashed_password=hash_password_safe("Bench@123"))
db.add(u)
db.commit()
db.refresh(u)

QUERY_COUNT = {"n": 0}


@event.listens_for(engine, "before_cursor_execute")
def _count(conn, cursor, statement, parameters, context, executemany):
    QUERY_COUNT["n"] += 1


CATS = ["Groceries", "Food & Dining", "Transport", "Shopping", "Entertainment", "Utilities", "Rent", "Health"]
MERCH = ["Swiggy", "BigBasket", "Uber", "Amazon", "Netflix", "BESCOM", "Store", "Pharmacy"]
random.seed(7)


def bulk(n, start):
    rows = []
    base = date(2024, 1, 1)
    for i in range(n):
        d = base + timedelta(days=random.randint(0, 1000))
        rows.append(Transaction(
            user_id=u.id, type="income" if i % 9 == 0 else "expense",
            amount=Decimal(str(random.randint(50, 5000))), currency="INR",
            category_name=random.choice(CATS), merchant=random.choice(MERCH),
            description="bench", date=d, dedup_hash=f"h{start + i}"))
    db.bulk_save_objects(rows)
    db.commit()


def measure(fn):
    db.expire_all()
    QUERY_COUNT["n"] = 0
    t0 = time.perf_counter()
    out = fn()
    t1 = time.perf_counter()
    return out, (t1 - t0) * 1000, QUERY_COUNT["n"]


from app.analytics.service import compute_summary, dashboard  # noqa: E402
from app.analytics.advanced import smart_insights  # noqa: E402
from app.ml.forecasting.model import forecast  # noqa: E402

results = {}
total = 0
for target in (1000, 10000, 49000):
    bulk(target - total, total)
    total = target
    entry = {}
    _, ms, q = measure(lambda: compute_summary(db, u.id))
    entry["summary"] = {"ms": round(ms), "queries": q}
    tracemalloc.start()
    _, ms, q = measure(lambda: dashboard(db, u.id))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    entry["dashboard"] = {"ms": round(ms), "queries": q, "tracemalloc_peak_mb": round(peak / 1e6, 1)}
    _, ms, q = measure(lambda: smart_insights(db, u.id))
    entry["insights"] = {"ms": round(ms), "queries": q}
    _, ms, q = measure(lambda: forecast(db, u.id, 30))
    entry["forecast"] = {"ms": round(ms), "queries": q}
    results[str(target)] = entry
    print(f"n={target}: " + " | ".join(
        f"{k} {v['ms']}ms/{v['queries']}q" + (f"/{v['tracemalloc_peak_mb']}MB" if "tracemalloc_peak_mb" in v else "")
        for k, v in entry.items()))

out_path = sys.argv[1] if len(sys.argv) > 1 else "benchmark.json"
os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"wrote {out_path}")
