"""Stage 4: subscription_overrides + payment_reminders tables.

Additive only. Downgrade drops both tables (override/reminder data is
user-entered; downgrading a production database would lose it — restore
from backup instead of downgrading in production).

Revision ID: 004_subs_calendar
Revises: 003_health_snapshots
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_subs_calendar"
down_revision: Union[str, None] = "003_health_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("merchant_key", sa.String(), nullable=False),
        sa.Column("merchant", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("custom_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("custom_frequency", sa.String(), nullable=True),
        sa.Column("custom_next_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscription_overrides_user_id", "subscription_overrides", ["user_id"])
    op.create_index("ix_sub_override_user_key", "subscription_overrides", ["user_id", "merchant_key"], unique=True)
    op.create_table(
        "payment_reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("recurrence", sa.String(), nullable=True),
        sa.Column("category_name", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_reminders_user_id", "payment_reminders", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_reminders_user_id", table_name="payment_reminders")
    op.drop_table("payment_reminders")
    op.drop_index("ix_sub_override_user_key", table_name="subscription_overrides")
    op.drop_index("ix_subscription_overrides_user_id", table_name="subscription_overrides")
    op.drop_table("subscription_overrides")
