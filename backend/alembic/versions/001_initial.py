"""initial schema — creates all tables from SQLAlchemy metadata (works SQLite + Postgres)"""
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    from alembic import op
    from app.core.database import Base
    from app.models import models  # noqa
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

def downgrade():
    from alembic import op
    from app.core.database import Base
    from app.models import models  # noqa
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
