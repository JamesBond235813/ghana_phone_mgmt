"""remove demo wording from organization and location display names"""

from alembic import op
import sqlalchemy as sa

revision = "0012_normalize_org_location_names"
down_revision = "0011_normalize_role_display_names"
branch_labels = None
depends_on = None

ORGANIZATION_NAMES = {
    "DEMO2-SZ": "深圳办公室与仓库",
    "DEMO2-GH": "加纳管理处",
}
LOCATION_NAMES = {
    "DEMO2-SZ-WH": "深圳仓/收货区",
    "DEMO2-GH-MGMT": "加纳管理处仓",
    "DEMO2-GH-STORE-A": "加纳门店 A",
    "DEMO2-GH-STORE-B": "加纳门店 B",
    "DEMO2-GH-REPAIR": "加纳维修区",
}

def upgrade() -> None:
    bind = op.get_bind()
    for code, name in ORGANIZATION_NAMES.items():
        bind.execute(sa.text("UPDATE organizations SET name = :name WHERE code = :code"), {"code": code, "name": name})
    for code, name in LOCATION_NAMES.items():
        bind.execute(sa.text("UPDATE locations SET name = :name WHERE code = :code"), {"code": code, "name": name})

def downgrade() -> None:
    pass
