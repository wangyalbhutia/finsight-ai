#!/usr/bin/env bash
# FinSight AI — independent verification harness. Run from repo root.
# Reports honest pass/fail per stage; exit code = number of failed stages.
set -u
FAIL=0
step() { echo; echo "=== $1 ==="; }
run() { if "$@"; then echo "PASS: $*"; else echo "FAIL: $*"; FAIL=$((FAIL+1)); fi; }

step "Backend tests"
ROOT="$(pwd)"
if [ -x backend/.venv/bin/python ]; then PY="$ROOT/backend/.venv/bin/python"; else PY="$(command -v python3)"; fi
(cd backend && "$PY" -m pytest -q) || { echo "FAIL: backend pytest"; FAIL=$((FAIL+1)); }

step "Backend import / health smoke"
(cd backend && "$PY" -c "from app.main import app; print('app imports OK')") || { echo "FAIL: app import"; FAIL=$((FAIL+1)); }

step "Alembic migration on clean SQLite"
TMPDB=$(mktemp -u /tmp/finsight_mig_XXXX.db)
(cd backend && DATABASE_URL="sqlite:///$TMPDB" "$PY" -m alembic upgrade head) || { echo "FAIL: alembic upgrade head"; FAIL=$((FAIL+1)); }
rm -f "$TMPDB"

step "Frontend typecheck + build"
if [ -f frontend/package.json ]; then
  (cd frontend && run npx tsc --noEmit)
  (cd frontend && run npm run build)
else
  echo "FAIL: frontend/package.json missing"; FAIL=$((FAIL+1))
fi

step "Docker Compose config"
if command -v docker >/dev/null 2>&1; then
  run docker compose config -q
else
  echo "SKIP: docker not available in this environment (config not validated)"
fi

echo; echo "=== Verification finished. Failed stages: $FAIL ==="
exit $FAIL
