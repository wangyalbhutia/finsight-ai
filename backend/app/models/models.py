from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Boolean, Text, Numeric, Float, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, default="")
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    # Multi-currency choice: user's primary currency (INR default). Analytics totals
    # are computed ONLY in this currency; other-currency txns are grouped separately
    # in totals_by_currency and never silently summed into primary totals.
    currency = Column(String, default="INR")
    preferred_currency = Column(String, default="INR")
    created_at = Column(DateTime(timezone=True), default=utcnow)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    family_id = Column(String, index=True, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class RevokedAccessToken(Base):
    """Denylist for access-token jti after logout (access tokens are otherwise stateless)."""
    __tablename__ = "revoked_access_tokens"
    id = Column(Integer, primary_key=True)
    jti = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, default="bank")
    currency = Column(String, default="INR")
    balance = Column(Numeric(14,2), default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    name = Column(String, nullable=False, index=True)
    type = Column(String, default="expense")
    icon = Column(String, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    category_name = Column(String, default="Uncategorized", index=True)
    type = Column(String, nullable=False, index=True)  # income, expense, transfer, refund
    amount = Column(Numeric(14,2), nullable=False)
    currency = Column(String, default="INR", index=True)
    merchant = Column(String, default="", index=True)
    description = Column(String, default="")
    notes = Column(Text, default="")
    date = Column(Date, nullable=False, index=True)
    is_recurring = Column(Boolean, default=False)
    dedup_hash = Column(String, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_txn_user_date", "user_id", "date"),
                      # Stage 2: composites matching the engine's grouped-query patterns
                      Index("ix_txn_user_type_date", "user_id", "type", "date"),
                      Index("ix_txn_user_currency_type", "user_id", "currency", "type"),
                      Index("ix_txn_user_category_date", "user_id", "category_name", "date"))

class Budget(Base):
    __tablename__ = "budgets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    category_name = Column(String, default="Overall", index=True)
    amount = Column(Numeric(14,2), nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    category_name = Column(String, default="Uncategorized")
    type = Column(String, default="expense")
    amount = Column(Numeric(14,2), nullable=False)
    merchant = Column(String, default="")
    description = Column(String, default="")
    frequency = Column(String, default="monthly")
    next_date = Column(Date, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class FinancialGoal(Base):
    __tablename__ = "financial_goals"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String, nullable=False)
    target_amount = Column(Numeric(14,2), nullable=False)
    current_amount = Column(Numeric(14,2), default=0)
    deadline = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class HealthScoreSnapshot(Base):
    """Stage 3: one health-score reading per user per day, written when the
    score is read, so changes can be explained against stored components."""
    __tablename__ = "health_score_snapshots"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    snapshot_date = Column(Date, nullable=False)
    score = Column(Float, nullable=False)
    grade = Column(String, nullable=False)
    components = Column(Text, nullable=False)  # JSON: {name: {score, weight, note, data_backed}}
    data_coverage_percent = Column(Float, nullable=False, default=0)
    currency = Column(String, default="INR")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_health_snapshot_user_date", "user_id", "snapshot_date"),)

class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    horizon_days = Column(Integer, nullable=False)
    predicted_amount = Column(Float, nullable=False)
    lower_bound = Column(Float, nullable=True)
    upper_bound = Column(Float, nullable=True)
    category_name = Column(String, default="Overall")
    model_version = Column(String, default="exp_smoothing_v1")
    mae = Column(Float, nullable=True)
    rmse = Column(Float, nullable=True)
    mape = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class AnomalyAlert(Base):
    __tablename__ = "anomaly_alerts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True, index=True)
    severity = Column(String, default="medium")  # low, medium, high
    reason = Column(Text, nullable=False)
    score = Column(Float, default=0.0)
    anomaly_type = Column(String, default="unusual_amount")
    status = Column(String, default="open")  # open, acknowledged, dismissed
    created_at = Column(DateTime(timezone=True), default=utcnow)

class AIConversation(Base):
    __tablename__ = "ai_conversations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String, default="Conversation")
    created_at = Column(DateTime(timezone=True), default=utcnow)

class AIMessage(Base):
    __tablename__ = "ai_messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String, nullable=False)
    detail = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)

class SubscriptionOverride(Base):
    """Stage 4: user's verdict on a detected subscription (confirm /
    dismiss / edit), keyed by the normalised merchant key so spelling
    variants share one override. Detection alone never sets this."""
    __tablename__ = "subscription_overrides"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    merchant_key = Column(String, nullable=False)
    merchant = Column(String, default="")
    status = Column(String, nullable=False)  # confirmed | dismissed
    custom_amount = Column(Numeric(14, 2), nullable=True)
    custom_frequency = Column(String, nullable=True)
    custom_next_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_sub_override_user_key", "user_id", "merchant_key", unique=True),)

class PaymentReminder(Base):
    """Stage 4: user-defined payment reminder shown on the financial
    calendar. Created only by the user — never inferred."""
    __tablename__ = "payment_reminders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String, nullable=False)
    amount = Column(Numeric(14, 2), nullable=True)
    due_date = Column(Date, nullable=False)
    recurrence = Column(String, default="none")  # none | weekly | monthly | yearly
    category_name = Column(String, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)

class StatementImport(Base):
    """Stage 5: audit record for a bank/UPI statement import. Stores only
    counts and the filename — never statement contents."""
    __tablename__ = "statement_imports"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    filename = Column(String, default="")
    format_detected = Column(String, default="bank_csv")
    total_rows = Column(Integer, default=0)
    accepted = Column(Integer, default=0)
    duplicates = Column(Integer, default=0)
    rejected = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)

class UserMemory(Base):
    """Stage 7 (Financial Memory): facts/preferences the user has chosen
    to store — preferences, merchant category corrections, life-event
    context, notes. Fully user-visible and user-deletable; never written
    silently by the system except merchant corrections the user makes."""
    __tablename__ = "user_memories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    category = Column(String, default="preference")  # preference | merchant_correction | life_event | note
    key = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_memory_user_key", "user_id", "category", "key"),)

class Notification(Base):
    """Stage 7: proactive briefing items generated deterministically from
    the user's own data (budget risk, insight warnings, goal milestones).
    Deduplicated by dedupe_key so a briefing never spams."""
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind = Column(String, nullable=False)
    severity = Column(String, default="info")
    title = Column(String, nullable=False)
    body = Column(Text, default="")
    dedupe_key = Column(String, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_notif_user_dedupe", "user_id", "dedupe_key"),)
