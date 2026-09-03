"""add admin and server query endpoints (metadata already present)"""
from alembic import op

revision = "0007_admin_queries_schema"
down_revision = "0006_stocktake_adjustment_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db import models  # noqa: F401
    from app.db.base import Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    pass
