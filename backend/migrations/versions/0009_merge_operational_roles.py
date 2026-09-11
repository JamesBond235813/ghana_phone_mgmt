"""merge the demo operational roles into the real station workgroups

The first demo fixture modelled every hand-off as a separate role.  In the
actual operation one Shenzhen warehouse operator performs receiving/inspection
and both packing steps, while one Ghana operations operator performs the
management-office receiving, picking/dispatch, return triage and repair
intake/QA steps.  This migration keeps the old role rows as inactive records,
reassigns their users to the canonical role, and gives the canonical role the
union of the old permissions.  No user row is deleted.

The migration is intentionally idempotent.  This is useful for databases that
were bootstrapped from an early development snapshot before Alembic was
introduced.  ``downgrade`` is a no-op because restoring a historical role
split would require a reviewed per-user assignment decision.
"""

from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa


revision = "0009_merge_operational_roles"
down_revision = "0008_usernames"
branch_labels = None
depends_on = None


# canonical code -> (display name, work group, description, legacy codes,
# published permission contract)
ROLE_MERGES: dict[str, tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = {
    "demo_sz_operations": (
        "深圳仓综合作业（收购验收/装托/装箱）",
        "SHENZHEN_OPERATIONS",
        "同一岗位完成深圳收购验收、装入托盘和装箱封装",
        ("demo_sz_buyer", "demo_sz_tray", "demo_sz_packer"),
        ("phone:view", "phone:edit", "tray:manage", "box:manage", "purchase:create"),
    ),
    "demo_ghana_operations": (
        "加纳管理处综合作业（到货/拣货/退回/维修质检）",
        "GHANA_OPERATIONS",
        "同一岗位完成加纳到货验收、仓库拣货发运、退回分诊及维修建单/QA",
        (
            "demo_gh_receiver",
            "demo_gh_warehouse",
            "demo_gh_return",
            "demo_repair_intake",
            "demo_repair_qa",
        ),
        (
            "phone:view",
            "shipment:view",
            "receiving:unpack",
            "receiving:accept",
            "transfer:create",
            "return:receive",
            "inventory:issue",
            "inventory:receive",
            "tray:manage",
            "box:manage",
            "repair:create",
            "repair:approve",
            "report:view",
        ),
    ),
}


PERMISSION_NAMES = {
    "phone:view": "查看手机与轨迹",
    "phone:edit": "编辑手机资料",
    "tray:manage": "托盘装入/取出手机",
    "box:manage": "箱子装入/取出托盘",
    "purchase:create": "创建采购入库",
    "shipment:dispatch": "深圳跨境发运",
    "shipment:view": "查看发运单",
    "receiving:accept": "逐台验收",
    "receiving:unpack": "拆箱/拆托盘",
    "transfer:create": "创建调拨出库",
    "transfer:receive": "调拨收货",
    "inventory:issue": "库存出库",
    "inventory:receive": "库存入库",
    "sales:create": "创建销售单",
    "sales:approve": "审核销售单",
    "sales:cancel": "取消销售单",
    "return:create": "创建退回单",
    "return:receive": "接收退回手机",
    "repair:create": "创建维修单",
    "repair:receive": "维修接单",
    "repair:update": "填写维修结果",
    "repair:approve": "维修结果验收",
    "stocktake:submit": "提交盘点",
    "stocktake:adjust": "处理盘点差异",
    "report:view": "查看报表",
    "audit:view": "查看审计日志",
    "user:manage": "用户管理",
    "role:manage": "角色与权限管理",
}


def _column_names(bind: sa.Connection, table: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(bind).get_columns(table)}


def _ensure_permission(bind: sa.Connection, code: str) -> int:
    row = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
    ).first()
    if row is not None:
        return int(row[0])
    result = bind.execute(
        sa.text("INSERT INTO permissions (code, name) VALUES (:code, :name)"),
        {"code": code, "name": PERMISSION_NAMES.get(code, code)},
    )
    # Textual INSERT statements do not consistently expose
    # ``inserted_primary_key`` on every SQLAlchemy dialect, so resolve by the
    # unique natural key after inserting.
    return int(
        bind.execute(
            sa.text("SELECT id FROM permissions WHERE code = :code"), {"code": code}
        ).scalar_one()
    )


def _insert_if_missing(
    bind: sa.Connection,
    table: str,
    where_sql: str,
    where_params: dict[str, object],
    insert_sql: str,
    insert_params: dict[str, object],
) -> None:
    if bind.execute(sa.text(f"SELECT 1 FROM {table} WHERE {where_sql} LIMIT 1"), where_params).first() is None:
        bind.execute(sa.text(insert_sql), insert_params)


def _merge_one(
    bind: sa.Connection,
    canonical_code: str,
    name: str,
    work_group: str,
    description: str,
    legacy_codes: Iterable[str],
    permission_codes: Iterable[str],
) -> None:
    all_codes = (canonical_code, *tuple(legacy_codes))
    placeholders = ", ".join(f":code_{index}" for index, _ in enumerate(all_codes))
    params = {f"code_{index}": code for index, code in enumerate(all_codes)}
    rows = list(
        bind.execute(
            sa.text(f"SELECT id, code FROM roles WHERE code IN ({placeholders}) ORDER BY id"),
            params,
        ).mappings()
    )

    canonical = next((row for row in rows if row["code"] == canonical_code), None)
    if canonical is None:
        if rows:
            # Reuse the oldest role id so references remain stable where
            # possible.  The unique code constraint is safe because canonical
            # was absent in the query above.
            survivor = rows[0]
            bind.execute(
                sa.text(
                    "UPDATE roles SET code = :canonical, name = :name, is_active = 1 "
                    ", work_group = :work_group, description = :description "
                    "WHERE id = :role_id"
                ),
                {
                    "canonical": canonical_code,
                    "name": name,
                    "work_group": work_group,
                    "description": description,
                    "role_id": survivor["id"],
                },
            )
            canonical_id = int(survivor["id"])
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO roles (code, name, is_active, work_group, description) "
                    "VALUES (:code, :name, 1, :work_group, :description)"
                ),
                {
                    "code": canonical_code,
                    "name": name,
                    "work_group": work_group,
                    "description": description,
                },
            )
            canonical_id = int(
                bind.execute(
                    sa.text("SELECT id FROM roles WHERE code = :code"),
                    {"code": canonical_code},
                ).scalar_one()
            )
    else:
        canonical_id = int(canonical["id"])
        bind.execute(
            sa.text(
                "UPDATE roles SET name = :name, is_active = 1 WHERE id = :role_id"
            ),
            {"name": name, "role_id": canonical_id},
        )
        bind.execute(
            sa.text(
                "UPDATE roles SET work_group = :work_group, description = :description "
                "WHERE id = :role_id"
            ),
            {
                "work_group": work_group,
                "description": description,
                "role_id": canonical_id,
            },
        )

    role_ids = [int(row["id"]) for row in rows]
    if canonical_id not in role_ids:
        role_ids.append(canonical_id)
    role_placeholders = ", ".join(f":role_{index}" for index, _ in enumerate(role_ids))
    role_params = {f"role_{index}": role_id for index, role_id in enumerate(role_ids)}

    # Preserve all users attached to any old role, but give them one canonical
    # UserRole link.  Other unrelated roles on the same user are untouched.
    user_rows = list(
        bind.execute(
            sa.text(
                f"SELECT DISTINCT user_id FROM user_roles "
                f"WHERE role_id IN ({role_placeholders})"
            ),
            role_params,
        ).scalars()
    )
    for user_id in user_rows:
        _insert_if_missing(
            bind,
            "user_roles",
            "user_id = :user_id AND role_id = :role_id",
            {"user_id": user_id, "role_id": canonical_id},
            "INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)",
            {"user_id": user_id, "role_id": canonical_id},
        )
    bind.execute(
        sa.text(
            f"DELETE FROM user_roles WHERE role_id IN ({role_placeholders}) "
            "AND role_id <> :canonical_id"
        ),
        {**role_params, "canonical_id": canonical_id},
    )

    # Canonical permissions are an exact union of the published role
    # contract.  Legacy role rows retain no permissions so an accidentally
    # reactivated legacy role cannot silently grant stale access.
    bind.execute(
        sa.text("DELETE FROM role_permissions WHERE role_id = :role_id"),
        {"role_id": canonical_id},
    )
    for code in permission_codes:
        permission_id = _ensure_permission(bind, code)
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "VALUES (:role_id, :permission_id)"
            ),
            {"role_id": canonical_id, "permission_id": permission_id},
        )
    bind.execute(
        sa.text(
            f"DELETE FROM role_permissions WHERE role_id IN ({role_placeholders}) "
            "AND role_id <> :canonical_id"
        ),
        {**role_params, "canonical_id": canonical_id},
    )

    # Keep old rows for audit/configuration history, but make their status
    # explicit.  Include the canonical code in the name so an old admin UI
    # that does not yet filter is still understandable.
    legacy_ids = [role_id for role_id in role_ids if role_id != canonical_id]
    for role_id in legacy_ids:
        bind.execute(
            sa.text(
                "UPDATE roles SET is_active = 0, name = :legacy_name, "
                "work_group = :work_group, description = :description WHERE id = :role_id"
            ),
            {
                "legacy_name": f"{name}（已合并）",
                "work_group": f"LEGACY_{work_group}",
                "description": f"历史角色，权限已合并至 {canonical_code}",
                "role_id": role_id,
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    columns = _column_names(bind, "roles")
    if "is_active" not in columns:
        op.add_column(
            "roles",
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
    if "work_group" not in columns:
        op.add_column("roles", sa.Column("work_group", sa.String(length=64), nullable=True))
    if "description" not in columns:
        op.add_column("roles", sa.Column("description", sa.String(length=512), nullable=True))

    for code, (name, work_group, description, legacy_codes, permissions) in ROLE_MERGES.items():
        _merge_one(bind, code, name, work_group, description, legacy_codes, permissions)

    # Populate metadata for the pre-existing administrator without touching
    # its permission links or user assignment.
    bind.execute(
        sa.text(
            "UPDATE roles SET is_active = 1, work_group = :work_group, "
            "description = :description WHERE code = 'super_admin'"
        ),
        {
            "work_group": "SYSTEM",
            "description": "系统初始化、账号权限和审计管理",
        },
    )


def downgrade() -> None:
    # Re-splitting users and scopes cannot be inferred safely.  Keep the
    # merged configuration and require an explicit, reviewed data migration.
    pass
