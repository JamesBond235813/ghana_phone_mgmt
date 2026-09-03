"""add logistics, transfer, sales and return tables

Revision ID: 0002_logistics_sales_schema
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_logistics_sales_schema"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The first development migration was metadata-driven. create_all is
    # intentionally retained here as an idempotent compatibility bridge for
    # databases created by that migration before the logistics models existed.
    from app.db import models  # noqa: F401
    from app.db.base import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Do not drop business tables automatically in a production downgrade.
    # A reviewed, explicit rollback migration is required for deployment.
    pass
