"""add username login identifier and allow username-only accounts"""
from alembic import op
import sqlalchemy as sa


revision = "0008_usernames"
down_revision = "0007_admin_queries_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
