"""Stage 2: composite indexes for the Intelligence Engine's grouped queries.

Adds (user_id, type, date), (user_id, currency, type) and
(user_id, category_name, date) indexes on transactions. Purely additive —
no data changes; downgrade drops only these indexes.

Revision ID: 002_txn_indexes
Revises: 001_baseline
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_txn_indexes"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = [
    ("ix_txn_user_type_date", ["user_id", "type", "date"]),
    ("ix_txn_user_currency_type", ["user_id", "currency", "type"]),
    ("ix_txn_user_category_date", ["user_id", "category_name", "date"]),
]


def upgrade() -> None:
    for name, cols in INDEXES:
        op.create_index(name, "transactions", cols, unique=False)


def downgrade() -> None:
    for name, _cols in reversed(INDEXES):
        op.drop_index(name, table_name="transactions")
