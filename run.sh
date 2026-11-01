#!/usr/bin/env bash
# FinSight AI — one-command launcher (frontend + backend)
# First run installs everything and seeds demo data. Later runs just start.
# Usage:  ./run.sh          (Ctrl+C stops both servers)
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"

echo "==> FinSight AI starting from $ROOT"

# ---------- Backend setup (first run only) ----------
if [ ! -x backend/.venv/bin/uvicorn ]; then
  echo "==> First run: setting up backend (venv + dependencies)…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -f backend/finsight.db ]; then
  echo "==> First run: creating database + demo data (demo@finsight.ai / Demo@1234)…"
  (cd backend && .venv/bin/python -m app.seed)
fi

# ---------- Frontend setup (first run only) ----------
if [ ! -d frontend/node_modules ]; then
  echo "==> First run: installing frontend dependencies…"
  (cd frontend && npm install)
fi
[ -f frontend/.env.local ] || cp frontend/.env.example frontend/.env.local

# ---------- Start both ----------
cleanup() { echo; echo "==> Stopping FinSight AI…"; kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "==> Starting backend  → http://localhost:8000  (docs: http://localhost:8000/docs)"
(cd backend && .venv/bin/uvicorn app.main:app --port 8000) &
BACKEND_PID=$!

for i in $(seq 1 30); do
  curl -s http://localhost:8000/health >/dev/null 2>&1 && break
  sleep 1
done
curl -s http://localhost:8000/health >/dev/null 2>&1 && echo "==> Backend is up" || echo "!! Backend did not respond on :8000 — check the logs above"

echo "==> Starting frontend → http://localhost:3000"
echo "==> Open http://localhost:3000 and log in: demo@finsight.ai / Demo@1234"
(cd frontend && npm run dev)
