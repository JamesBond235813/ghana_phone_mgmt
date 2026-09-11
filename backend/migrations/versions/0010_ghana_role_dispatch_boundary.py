"""keep international shipment dispatch as a Shenzhen-only permission

The Ghana warehouse workgroup sends stock to stores through transfer orders;
it does not create/confirm a cross-border ``Shipment``.  A small follow-up
migration makes that boundary explicit for databases that already applied
0009 before the role contract was refined.  It is safe to run repeatedly.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_ghana_dispatch_boundary"
down_revision = "0009_merge_operational_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    role_id = bind.execute(
        sa.text("SELECT id FROM roles WHERE code = :code"),
        {"code": "demo_ghana_operations"},
    ).scalar()
    permission_id = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {"code": "shipment:dispatch"},
    ).scalar()
    if role_id is not None and permission_id is not None:
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions "
                "WHERE role_id = :role_id AND permission_id = :permission_id"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )


def downgrade() -> None:
    # The previous grant was semantically incorrect; do not silently restore
    # it during a downgrade.
    pass
