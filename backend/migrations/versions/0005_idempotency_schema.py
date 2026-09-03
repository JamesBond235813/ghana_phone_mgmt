"""add idempotency records"""
from alembic import op

revision = "0005_idempotency_schema"
down_revision = "0004_stocktake_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db import models  # noqa: F401
    from app.db.base import Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    pass
