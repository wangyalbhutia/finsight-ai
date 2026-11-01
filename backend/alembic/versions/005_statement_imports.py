"""Stage 5: statement_imports audit table. Additive only.

Revision ID: 005_statement_imports
Revises: 004_subs_calendar
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_statement_imports"
down_revision: Union[str, None] = "004_subs_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "statement_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("format_detected", sa.String(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("accepted", sa.Integer(), nullable=True),
        sa.Column("duplicates", sa.Integer(), nullable=True),
        sa.Column("rejected", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_statement_imports_user_id", "statement_imports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_statement_imports_user_id", table_name="statement_imports")
    op.drop_table("statement_imports")
