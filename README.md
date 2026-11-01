# FinSight AI
AI-powered personal finance analytics & expense prediction — understand where your money goes, forecast where it will go, detect unusual spending, and chat with an AI financial assistant grounded in your real data. Primary currency INR (₹), multi-currency aware.

## Architecture
Next.js (TypeScript, Tailwind, Recharts) → FastAPI (Python, SQLAlchemy 2.0) → PostgreSQL 16 (SQLite fallback for local dev/tests). ML: TF-IDF + Logistic Regression categorisation, Moving Average / Exponential Smoothing forecasting with chronological backtests, MAD + Isolation Forest anomaly detection. AI assistant: orchestrator + Analytics / Prediction / Anomaly / Recommendation agents using read-only, user-scoped tools; the LLM only explains deterministic results, with a template fallback when no LLM key is set.

Docs: [Architecture](docs/ARCHITECTURE.md) · [Database & API](docs/DATABASE_AND_API.md) · [Verification protocol](docs/VERIFICATION.md)

## Run locally (without Docker)
```bash
# Backend  (terminal 1)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.seed            # demo@finsight.ai / Demo@1234, ~390 seeded transactions
.venv/bin/uvicorn app.main:app --port 8000
# Frontend (terminal 2)
cd frontend
cp .env.example .env.local
npm install && npm run dev              # http://localhost:3000
```

## Run with Docker Compose
```bash
cp .env.example .env
docker compose up --build               # frontend :3000, backend :8000, Postgres :5432
```

## Tests & verification
```bash
cd backend && .venv/bin/python -m pytest tests/ -q     # backend suite
cd frontend && npx tsc --noEmit && npm run lint && npm test && npm run build
bash scripts/verify.sh                                  # full independent verification harness
```

## Demo account (seed data only — development/demonstration)
`demo@finsight.ai` / `Demo@1234` after running the seed script. Seed data is synthetic.
# finsight-ai
