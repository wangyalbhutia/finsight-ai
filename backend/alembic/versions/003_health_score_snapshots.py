"""Stage 3: health_score_snapshots table (one score reading per user/day).

Additive only — creates one new table and its index; no existing data is
touched. Downgrade drops the table (snapshots are derived data and can be
recomputed, so this is safe).

Revision ID: 003_health_snapshots
Revises: 002_txn_indexes
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_health_snapshots"
down_revision: Union[str, None] = "002_txn_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_score_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(), nullable=False),
        sa.Column("components", sa.Text(), nullable=False),
        sa.Column("data_coverage_percent", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_score_snapshots_user_id", "health_score_snapshots", ["user_id"])
    op.create_index("ix_health_snapshot_user_date", "health_score_snapshots", ["user_id", "snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_health_snapshot_user_date", table_name="health_score_snapshots")
    op.drop_index("ix_health_score_snapshots_user_id", table_name="health_score_snapshots")
    op.drop_table("health_score_snapshots")
