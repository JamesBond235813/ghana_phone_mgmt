"""remove demo wording from canonical role display names"""

from alembic import op
import sqlalchemy as sa


revision = "0011_normalize_role_display_names"
# Keep this identifier aligned with the revision declared by
# 0010_ghana_role_dispatch_boundary.py.
down_revision = "0010_ghana_dispatch_boundary"
branch_labels = None
depends_on = None


ROLE_NAMES = {
    "demo_sz_operations": "深圳仓综合作业（收购验收/装托/装箱）",
    "demo_sz_dispatch": "深圳发运",
    "demo_ghana_operations": "加纳管理处综合作业（到货/拣货/退回/维修质检）",
    "demo_store_a_receiver": "门店A收货",
    "demo_store_a_clerk": "门店A销售退回",
    "demo_store_a_supervisor": "门店A主管",
    "demo_store_b_operator": "门店B串货作业",
    "demo_return_packer": "门店退回打包",
    "demo_repair_tech": "维修技师",
    "demo_auditor": "报表审计盘点",
}


def upgrade() -> None:
    bind = op.get_bind()
    # Alembic creates this bookkeeping column as VARCHAR(32) by default;
    # this revision id is longer than that on MySQL.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    for code, name in ROLE_NAMES.items():
        bind.execute(
            sa.text("UPDATE roles SET name = :name WHERE code = :code"),
            {"code": code, "name": name},
        )


def downgrade() -> None:
    # The previous labels were environment/demo-specific wording and are not
    # restored on downgrade to avoid reintroducing misleading role names.
    pass
