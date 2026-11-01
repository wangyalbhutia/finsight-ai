import os, sys
os.environ["DATABASE_URL"] = "sqlite:///./test_finsight.db"
# ensure fresh DB file per run handled in fixture
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from app.core.database import Base, engine, SessionLocal
from app.main import app
from fastapi.testclient import TestClient

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # keep file for inspection

@pytest.fixture()
def client():
    return TestClient(app)

@pytest.fixture()
def db():
    s = SessionLocal(); yield s; s.close()

def make_user(client, email):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "Test@1234", "full_name": "T"})
    assert r.status_code == 201, r.text
    data = r.json()
    return data, {"Authorization": f"Bearer {data['access_token']}"}

@pytest.fixture()
def user1(client):
    return make_user(client, "u1@test.ai")

@pytest.fixture()
def user2(client):
    return make_user(client, "u2@test.ai")

def add_txn(client, headers, **kw):
    payload = {"type":"expense","amount":100,"category_name":"Food & Dining","merchant":"Swiggy","description":"swiggy food","date":"2026-01-15"}
    payload.update(kw)
    r = client.post("/api/v1/transactions", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()
