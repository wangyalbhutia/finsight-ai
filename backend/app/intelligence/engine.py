"""
Central Financial Intelligence Engine (Stage 2).

A single, user-scoped facade over FinSight's deterministic analytics,
advanced analytics and ML forecasting. Dashboard endpoints and AI agents
consume financial intelligence through this engine so every surface shows
the same numbers, computed once per request (results are memoised on the
instance — create one engine per request/task, never share across users).

Every engine response can be wrapped in a typed envelope that separates
historical facts, forecasts, assumptions and recommendations, and carries
data-freshness and model-version metadata. The engine is read-only: it
never writes financial data (forecast persistence inside the ML module is
unchanged, pre-existing behavior).
"""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics import advanced, service
from app.models.models import Transaction

ENGINE_VERSION = "intelligence_engine_v1"


class FinancialIntelligenceEngine:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._cache = {}

    def _cached(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # ---- core analytics (facts) ----
    def summary(self, year=None, month=None):
        return self._cached(f"summary:{year}:{month}",
                            lambda: service.compute_summary(self.db, self.user_id, year, month))

    def category_breakdown(self, year=None, month=None):
        return self._cached(f"cats:{year}:{month}",
                            lambda: service.category_breakdown(self.db, self.user_id, year, month))

    def trends(self):
        return self._cached("trends", lambda: service.trends(self.db, self.user_id))

    def recurring(self):
        return self._cached("recurring", lambda: service.recurring_expenses(self.db, self.user_id))

    def dashboard(self, year=None, month=None):
        return self._cached(f"dashboard:{year}:{month}",
                            lambda: service.dashboard(self.db, self.user_id, year, month))

    # ---- advanced analytics ----
    def health_score(self):
        return self._cached("health", lambda: advanced.financial_health_score(self.db, self.user_id))

    def insights(self):
        return self._cached("insights", lambda: advanced.smart_insights(self.db, self.user_id))

    def subscriptions(self):
        return self._cached("subs", lambda: advanced.detect_subscriptions(self.db, self.user_id))

    def budget_forecast(self):
        return self._cached("bf", lambda: advanced.budget_forecast(self.db, self.user_id))

    def cashflow(self, horizon_days=30):
        return self._cached(f"cf:{horizon_days}",
                            lambda: advanced.cashflow_projection(self.db, self.user_id, horizon_days))

    def affordability(self, item_name, cost, months):
        return advanced.affordability(self.db, self.user_id, item_name, cost, months)

    # ---- Stage 3 ----
    def cashflow_timeline(self, horizon_days=30):
        return self._cached(f"cft:{horizon_days}",
                            lambda: advanced.cashflow_timeline(self.db, self.user_id, horizon_days))

    def profile(self):
        """Digital Twin: computed from this user's records via this engine
        (see app/intelligence/profile.py). Facts only, gaps labelled."""
        from app.intelligence.profile import build_profile
        return self._cached("profile", lambda: build_profile(self.db, self.user_id, self))

    # ---- envelope / freshness ----
    def freshness(self):
        def _f():
            count, latest = self.db.query(func.count(Transaction.id), func.max(Transaction.date)).filter(
                Transaction.user_id == self.user_id).one()
            return {"transaction_count": count,
                    "latest_transaction_date": latest.isoformat() if latest else None}
        return self._cached("freshness", _f)

    def envelope(self, kind, payload, model_version=None):
        """kind: 'fact' | 'forecast' | 'assumption' | 'recommendation'."""
        return {"kind": kind, "engine_version": ENGINE_VERSION,
                "model_version": model_version,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "data_freshness": self.freshness(), "payload": payload}

    def overview(self):
        """One-shot intelligence overview for dashboards/agents: the shared
        summary + health + top insights + subscription totals, all computed
        through this single engine instance."""
        payload = {
            "summary": self.summary(),
            "health_score": self.health_score(),
            "insights": self.insights(),
            "subscriptions": self.subscriptions(),
            "budget_forecast": self.budget_forecast(),
        }
        return self.envelope("fact", payload)


def get_engine(db: Session, user_id: int) -> FinancialIntelligenceEngine:
    return FinancialIntelligenceEngine(db, user_id)
