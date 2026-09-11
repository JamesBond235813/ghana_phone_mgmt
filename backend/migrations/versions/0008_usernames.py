"""add username login identifier and allow username-only accounts"""
from alembic import op
import sqlalchemy as sa


revision = "0008_usernames"
down_revision = "0007_admin_queries_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The early development migrations use ``Base.metadata.create_all``.  A
    # fresh database therefore already contains columns/indexes introduced by
    # later ORM models, while an older database may not.  Keep this migration
    # safe for both shapes instead of failing with duplicate-column/index
    # errors (which previously forced operators to stamp 0008 manually).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {str(item["name"]): item for item in inspector.get_columns("users")}
    if "username" not in columns:
        op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))

    # ``unique=True, index=True`` in the ORM can produce a dialect-specific
    # index name.  Reuse any existing unique username index; otherwise create
    # the canonical name used by this migration.
    has_username_unique_index = any(
        bool(index.get("unique")) and list(index.get("column_names") or []) == ["username"]
        for index in inspector.get_indexes("users")
    )
    if not has_username_unique_index:
        op.create_index("ix_users_username", "users", ["username"], unique=True)

    if not bool(columns.get("phone", {}).get("nullable", True)):
        op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "phone", existing_type=sa.String(length=32), nullable=False)
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
