"""Seed a coherent, repeatable local demo dataset.

The demo is deliberately written as a database snapshot rather than by calling
the HTTP/domain mutation endpoints.  That keeps the fixture deterministic and
lets it contain both in-progress and completed work orders.  Only rows using
the ``DEMO2-`` prefix (and the users listed below) are created or updated; no
existing production-looking rows are deleted.

Run from ``backend/`` so that the repository's ``.env`` is loaded::

    PYTHONPATH=. ../.venv/bin/python scripts/seed_demo_data.py

The demo accounts all use the password supplied for this local exercise.  The
password is intentionally short for convenient walkthroughs and must never be
used outside a development database.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.permissions import PermissionCode, ScopeKind
from app.core.roles import LEGACY_ROLE_TO_CANONICAL, ROLE_METADATA
from app.core.security import hash_password, verify_password
from app.db.models import (
    Box,
    InventoryTransaction,
    Location,
    Organization,
    Permission,
    PhoneDevice,
    PhoneTrayRelation,
    PurchaseItem,
    PurchaseOrder,
    ReceivingItem,
    ReceivingOrder,
    RepairContainer,
    RepairItem,
    RepairOrder,
    ReturnContainer,
    ReturnItem,
    ReturnOrder,
    Role,
    RolePermission,
    SalesContainer,
    SalesItem,
    SalesOrder,
    Shipment,
    ShipmentContainer,
    ShipmentItem,
    StocktakeItem,
    StocktakeOrder,
    Tray,
    TrayBoxRelation,
    TransferContainer,
    TransferItem,
    TransferOrder,
    User,
    UserRole,
    UserScope,
)
from app.domain.enums import ContainerKind, DocumentStatus, PhoneStatus


DEMO_PREFIX = "DEMO2-"
DEMO_PASSWORD = os.environ.get("GHANA_DEMO_PASSWORD", "888888")
# A fixed clock makes reruns easy to compare while still looking like a recent
# working day in the local Ghana timezone (stored as UTC in MySQL).
BASE_TIME = datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)


def demo_imei(index: int) -> str:
    """Return a deterministic, Luhn-valid 15-digit IMEI."""

    # The 0027 prefix intentionally differs from the old, flawed demo seed so
    # both fixtures can coexist without colliding on the unique IMEI column.
    stem = f"3520990027{index:04d}"
    total = 0
    for position, digit in enumerate(reversed(stem)):
        value = int(digit) * (2 if position % 2 == 0 else 1)
        total += value // 10 + value % 10
    return stem + str((10 - total % 10) % 10)


@dataclass(frozen=True)
class PhoneSpec:
    index: int
    status: PhoneStatus
    organization_key: str | None
    location_key: str | None
    tray_key: str | None = None
    imei2: bool = False
    condition: str = "良好"


def build_phone_specs() -> dict[int, PhoneSpec]:
    """Describe the final physical/status snapshot for each demo phone."""

    specs: dict[int, PhoneSpec] = {}

    def add(
        indexes: range | list[int],
        status: PhoneStatus,
        organization_key: str | None,
        location_key: str | None,
        tray_key: str | None = None,
        *,
        imei2: set[int] | None = None,
        condition: str = "良好",
    ) -> None:
        for index in indexes:
            specs[index] = PhoneSpec(
                index=index,
                status=status,
                organization_key=organization_key,
                location_key=location_key,
                tray_key=tray_key,
                imei2=bool(imei2 and index in imei2),
                condition=condition,
            )

    add(range(1, 7), PhoneStatus.SHENZHEN_STOCK, "sz", "sz_wh")
    add(range(7, 11), PhoneStatus.IN_TRAY, "sz", "sz_wh", "sz_open", imei2={7})
    add(range(11, 14), PhoneStatus.IN_BOX, "sz", "sz_wh", "sz_box_a")
    add(range(14, 17), PhoneStatus.IN_BOX, "sz", "sz_wh", "sz_box_b")
    add(range(17, 21), PhoneStatus.IN_TRANSIT, None, None, "sz_inbound")
    add(range(21, 25), PhoneStatus.GHANA_PENDING_INSPECTION, "gh", "gh_mgmt", imei2={21})
    add(range(25, 31), PhoneStatus.GHANA_STOCK, "gh", "gh_mgmt", "gh_available")
    add(range(31, 35), PhoneStatus.GHANA_STOCK, "gh", "gh_mgmt")
    add(range(35, 39), PhoneStatus.TRANSFERRING, None, None, "to_store_a")
    # Keep one store-A phone in SALE_PENDING so the supervisor can exercise
    # the maker/checker confirmation flow immediately after login.
    add(range(39, 41), PhoneStatus.STORE_STOCK, "gh", "store_a", "store_a")
    add([41], PhoneStatus.SALE_PENDING, "gh", "store_a", "store_a")
    add([42], PhoneStatus.SOLD, None, None)
    add([43], PhoneStatus.RETURN_PENDING_CHECK, None, None, "return_transit", imei2={43})
    # Returned phones are first booked into the management office; the
    # separate triage event below moves this sample into the repair area.
    add([44], PhoneStatus.WAITING_REPAIR, "gh", "repair", "repair")
    add([45], PhoneStatus.REPAIRING, "gh", "repair", "repair")
    add([46], PhoneStatus.REPAIR_PENDING_ACCEPTANCE, "gh", "repair", "repair", imei2={46})
    add([47], PhoneStatus.AVAILABLE_AGAIN, "gh", "gh_mgmt")
    add([48], PhoneStatus.FROZEN, "gh", "gh_mgmt", condition="待核查/外观损坏")
    add([49], PhoneStatus.LOST_OR_SCRAPPED, None, None, condition="报损/遗失")
    add([50], PhoneStatus.STORE_STOCK, "gh", "store_b", "store_b")
    add([51], PhoneStatus.TRANSFERRING, None, None)
    add([52], PhoneStatus.STORE_STOCK, "gh", "store_a")
    return specs


ORGANIZATION_SPECS: dict[str, tuple[str, str, str]] = {
    "sz": (f"{DEMO_PREFIX}SZ", "深圳办公室与仓库", "CN"),
    "gh": (f"{DEMO_PREFIX}GH", "加纳管理处", "GH"),
}

LOCATION_SPECS: dict[str, tuple[str, str, str, str]] = {
    "sz_wh": (f"{DEMO_PREFIX}SZ-WH", "深圳仓/收货区", "warehouse", "sz"),
    "gh_mgmt": (f"{DEMO_PREFIX}GH-MGMT", "加纳管理处仓", "warehouse", "gh"),
    "store_a": (f"{DEMO_PREFIX}GH-STORE-A", "加纳门店 A", "store", "gh"),
    "store_b": (f"{DEMO_PREFIX}GH-STORE-B", "加纳门店 B", "store", "gh"),
    "repair": (f"{DEMO_PREFIX}GH-REPAIR", "加纳维修区", "repair", "gh"),
}

# code, location key (None means in transit), seal code
BOX_SPECS: dict[str, tuple[str, str | None, str]] = {
    "sz_ready": (f"{DEMO_PREFIX}BOX-SZ-READY", "sz_wh", "SZ-SEAL-READY"),
    "sz_inbound": (f"{DEMO_PREFIX}BOX-SZ-INBOUND", None, "SZ-SEAL-INBOUND"),
    "sz_checking": (f"{DEMO_PREFIX}BOX-SZ-CHECKING", "gh_mgmt", "SZ-SEAL-CHECKING"),
    "sz_history": (f"{DEMO_PREFIX}BOX-SZ-HISTORY", "gh_mgmt", "SZ-SEAL-HISTORY"),
    "gh_available": (f"{DEMO_PREFIX}BOX-GH-AVAILABLE", "gh_mgmt", "GH-SEAL-AVAILABLE"),
    "to_store_a": (f"{DEMO_PREFIX}BOX-TO-STORE-A", None, "TRF-SEAL-STORE-A"),
    "return_transit": (f"{DEMO_PREFIX}BOX-RETURN-TRANSIT", None, "RET-SEAL-TRANSIT"),
    # A return is first received at the Ghana management office.  The
    # subsequent triage/repair hand-off is represented by a separate repair
    # container, so the received box must not already appear in the repair
    # area.
    "return_received": (f"{DEMO_PREFIX}BOX-RETURN-RECEIVED", "gh_mgmt", "RET-SEAL-RECEIVED"),
    "repair": (f"{DEMO_PREFIX}BOX-REPAIR", "repair", "REP-SEAL-REPAIR"),
    "store_b": (f"{DEMO_PREFIX}BOX-STORE-B", "store_b", "STORE-B-SEAL"),
}

# code, location key, containing box key (None means loose tray)
TRAY_SPECS: dict[str, tuple[str, str | None, str | None]] = {
    "sz_open": (f"{DEMO_PREFIX}TRAY-SZ-OPEN", "sz_wh", None),
    "sz_box_a": (f"{DEMO_PREFIX}TRAY-SZ-BOX-A", "sz_wh", "sz_ready"),
    "sz_box_b": (f"{DEMO_PREFIX}TRAY-SZ-BOX-B", "sz_wh", "sz_ready"),
    "sz_inbound": (f"{DEMO_PREFIX}TRAY-SZ-INBOUND", None, "sz_inbound"),
    "sz_checking": (f"{DEMO_PREFIX}TRAY-SZ-CHECKING", "gh_mgmt", "sz_checking"),
    "sz_history": (f"{DEMO_PREFIX}TRAY-SZ-HISTORY", "gh_mgmt", "sz_history"),
    "gh_available": (f"{DEMO_PREFIX}TRAY-GH-AVAILABLE", "gh_mgmt", "gh_available"),
    "to_store_a": (f"{DEMO_PREFIX}TRAY-TO-STORE-A", None, "to_store_a"),
    "store_a": (f"{DEMO_PREFIX}TRAY-STORE-A", "store_a", None),
    "return_transit": (f"{DEMO_PREFIX}TRAY-RETURN-TRANSIT", None, "return_transit"),
    "return_received": (f"{DEMO_PREFIX}TRAY-RETURN-RECEIVED", "gh_mgmt", "return_received"),
    "repair": (f"{DEMO_PREFIX}TRAY-REPAIR", "repair", "repair"),
    "store_b": (f"{DEMO_PREFIX}TRAY-STORE-B", "store_b", "store_b"),
    "sz_empty": (f"{DEMO_PREFIX}TRAY-SZ-EMPTY", "sz_wh", None),
    "gh_empty": (f"{DEMO_PREFIX}TRAY-GH-EMPTY", "gh_mgmt", None),
}


PERMISSION_NAMES: dict[PermissionCode, str] = {
    PermissionCode.PHONE_VIEW: "查看手机与轨迹",
    PermissionCode.PHONE_EDIT: "编辑手机资料",
    PermissionCode.TRAY_MANAGE: "托盘装入/取出手机",
    PermissionCode.BOX_MANAGE: "箱子装入/取出托盘",
    PermissionCode.PURCHASE_CREATE: "创建采购入库",
    PermissionCode.SHIPMENT_DISPATCH: "深圳跨境发运",
    PermissionCode.SHIPMENT_VIEW: "查看发运单",
    PermissionCode.RECEIVING_ACCEPT: "逐台验收",
    PermissionCode.RECEIVING_UNPACK: "拆箱/拆托盘",
    PermissionCode.TRANSFER_CREATE: "创建调拨出库",
    PermissionCode.TRANSFER_RECEIVE: "调拨收货",
    PermissionCode.INVENTORY_ISSUE: "库存出库",
    PermissionCode.INVENTORY_RECEIVE: "库存入库",
    PermissionCode.SALES_CREATE: "创建销售单",
    PermissionCode.SALES_APPROVE: "审核销售单",
    PermissionCode.SALES_CANCEL: "取消销售单",
    PermissionCode.RETURN_CREATE: "创建退回单",
    PermissionCode.RETURN_RECEIVE: "接收退回手机",
    PermissionCode.REPAIR_CREATE: "创建维修单",
    PermissionCode.REPAIR_RECEIVE: "维修接单",
    PermissionCode.REPAIR_UPDATE: "填写维修结果",
    PermissionCode.REPAIR_APPROVE: "维修结果验收",
    PermissionCode.STOCKTAKE_SUBMIT: "提交盘点",
    PermissionCode.STOCKTAKE_ADJUST: "处理盘点差异",
    PermissionCode.REPORT_VIEW: "查看报表",
    PermissionCode.AUDIT_VIEW: "查看审计日志",
    PermissionCode.USER_MANAGE: "用户管理",
    PermissionCode.ROLE_MANAGE: "角色与权限管理",
}


# The fixture now follows the real staffing model: one Shenzhen operator owns
# purchase inspection + tray/box packing, and one Ghana operations operator
# owns inbound receiving + picking/dispatch + returns triage + repair intake/QA.
# The repair technician remains a separate execution role.
ROLE_DEFS: dict[str, tuple[str, list[PermissionCode]]] = {
    "demo_sz_operations": (
        ROLE_METADATA["demo_sz_operations"].name,
        [
            PermissionCode.PHONE_VIEW,
            PermissionCode.PHONE_EDIT,
            PermissionCode.TRAY_MANAGE,
            PermissionCode.BOX_MANAGE,
            PermissionCode.PURCHASE_CREATE,
        ],
    ),
    "demo_sz_dispatch": (
        ROLE_METADATA["demo_sz_dispatch"].name,
        [
            PermissionCode.PHONE_VIEW,
            PermissionCode.SHIPMENT_VIEW,
            PermissionCode.SHIPMENT_DISPATCH,
            PermissionCode.INVENTORY_ISSUE,
        ],
    ),
    "demo_ghana_operations": (
        ROLE_METADATA["demo_ghana_operations"].name,
        [
            PermissionCode.PHONE_VIEW,
            PermissionCode.SHIPMENT_VIEW,
            PermissionCode.RECEIVING_UNPACK,
            PermissionCode.RECEIVING_ACCEPT,
            PermissionCode.TRANSFER_CREATE,
            PermissionCode.RETURN_RECEIVE,
            PermissionCode.INVENTORY_ISSUE,
            PermissionCode.INVENTORY_RECEIVE,
            PermissionCode.TRAY_MANAGE,
            PermissionCode.BOX_MANAGE,
            PermissionCode.REPAIR_CREATE,
            PermissionCode.REPAIR_APPROVE,
            PermissionCode.REPORT_VIEW,
        ],
    ),
    "demo_store_a_receiver": (ROLE_METADATA["demo_store_a_receiver"].name, [PermissionCode.PHONE_VIEW, PermissionCode.TRANSFER_RECEIVE, PermissionCode.RECEIVING_UNPACK, PermissionCode.RECEIVING_ACCEPT]),
    "demo_store_a_clerk": (ROLE_METADATA["demo_store_a_clerk"].name, [PermissionCode.PHONE_VIEW, PermissionCode.SALES_CREATE, PermissionCode.RETURN_CREATE, PermissionCode.STOCKTAKE_SUBMIT]),
    "demo_store_a_supervisor": (ROLE_METADATA["demo_store_a_supervisor"].name, [PermissionCode.PHONE_VIEW, PermissionCode.TRANSFER_CREATE, PermissionCode.SALES_APPROVE, PermissionCode.SALES_CANCEL, PermissionCode.STOCKTAKE_ADJUST, PermissionCode.REPORT_VIEW]),
    "demo_store_b_operator": (ROLE_METADATA["demo_store_b_operator"].name, [PermissionCode.PHONE_VIEW, PermissionCode.TRANSFER_CREATE, PermissionCode.TRANSFER_RECEIVE, PermissionCode.SALES_CREATE, PermissionCode.RETURN_CREATE, PermissionCode.STOCKTAKE_SUBMIT]),
    "demo_return_packer": (ROLE_METADATA["demo_return_packer"].name, [PermissionCode.PHONE_VIEW, PermissionCode.RETURN_CREATE, PermissionCode.TRAY_MANAGE, PermissionCode.BOX_MANAGE, PermissionCode.INVENTORY_ISSUE]),
    "demo_repair_tech": (ROLE_METADATA["demo_repair_tech"].name, [PermissionCode.PHONE_VIEW, PermissionCode.REPAIR_RECEIVE, PermissionCode.REPAIR_UPDATE]),
    "demo_auditor": (ROLE_METADATA["demo_auditor"].name, [PermissionCode.PHONE_VIEW, PermissionCode.REPORT_VIEW, PermissionCode.AUDIT_VIEW, PermissionCode.STOCKTAKE_SUBMIT, PermissionCode.STOCKTAKE_ADJUST]),
}

# username, display name, role code, default scope location (or None for ALL),
# and per-permission scope overrides.  An override may be a list to represent
# a multi-location workgroup (the Ghana operator works in both management and
# repair areas).  The Shenzhen purchase scope is deliberately location-level:
# the combined operator works at the Shenzhen receiving/packing station, not at
# every future location in the organization.
ScopeSpec = tuple[ScopeKind, str | None] | list[tuple[ScopeKind, str | None]]
USER_DEFS: list[tuple[str, str, str, str | None, dict[PermissionCode, ScopeSpec]]] = [
    ("szops", "深圳仓综合作业员", "demo_sz_operations", "sz_wh", {PermissionCode.PURCHASE_CREATE: (ScopeKind.LOCATION, "sz_wh")}),
    ("szdispatch", "深圳发运员", "demo_sz_dispatch", "sz_wh", {}),
    (
        "ghops",
        "加纳管理处综合作业员",
        "demo_ghana_operations",
        "gh_mgmt",
        {
            PermissionCode.PHONE_VIEW: [(ScopeKind.LOCATION, "gh_mgmt"), (ScopeKind.LOCATION, "repair")],
            PermissionCode.TRAY_MANAGE: [(ScopeKind.LOCATION, "gh_mgmt"), (ScopeKind.LOCATION, "repair")],
            PermissionCode.BOX_MANAGE: [(ScopeKind.LOCATION, "gh_mgmt"), (ScopeKind.LOCATION, "repair")],
            PermissionCode.REPORT_VIEW: [(ScopeKind.LOCATION, "gh_mgmt"), (ScopeKind.LOCATION, "repair")],
            PermissionCode.REPAIR_CREATE: (ScopeKind.LOCATION, "repair"),
            PermissionCode.REPAIR_APPROVE: (ScopeKind.LOCATION, "repair"),
        },
    ),
    ("storeareceive", "门店A收货员", "demo_store_a_receiver", "store_a", {}),
    ("storeaclerk", "门店A销售员", "demo_store_a_clerk", "store_a", {}),
    ("storeasupervisor", "门店A主管", "demo_store_a_supervisor", "store_a", {}),
    ("storeboperator", "门店B串货员", "demo_store_b_operator", "store_b", {}),
    ("returnpack", "门店退回打包员", "demo_return_packer", "store_a", {}),
    ("repairtech", "维修技师", "demo_repair_tech", "repair", {}),
    ("auditor", "审计盘点员", "demo_auditor", None, {}),
]

# Existing demo users are retained for audit/history but no longer represent
# separate jobs.  They are made inactive and their grants are removed; no
# User row is deleted.  Removing the links is intentional: an administrator
# must explicitly choose a current role and scope before reactivating an old
# alias, so a retired account can never regain access by accident.
LEGACY_USER_TO_CANONICAL: dict[str, str] = {
    "szbuyer": "szops",
    "sztray": "szops",
    "szpacker": "szops",
    "ghreceive": "ghops",
    "ghwarehouse": "ghops",
    "ghreturn": "ghops",
    "repairintake": "ghops",
    "repairqa": "ghops",
    # The first revision of this merge used ``ghanaops``; retain it as a
    # migrated alias when a developer has already run that revision.
    "ghanaops": "ghops",
}


async def get_or_create(
    session: AsyncSession,
    model: Any,
    lookup: dict[str, Any],
    values: dict[str, Any] | None = None,
) -> Any:
    conditions = [getattr(model, key) == value for key, value in lookup.items()]
    row = await session.scalar(select(model).where(*conditions))
    if row is None:
        row = model(**lookup, **(values or {}))
        session.add(row)
        await session.flush()
    else:
        for key, value in (values or {}).items():
            setattr(row, key, value)
    return row


async def ensure_organizations_and_locations(session: AsyncSession) -> tuple[dict[str, Organization], dict[str, Location]]:
    organizations: dict[str, Organization] = {}
    for key, (code, name, country) in ORGANIZATION_SPECS.items():
        organizations[key] = await get_or_create(
            session, Organization, {"code": code}, {"name": name, "country": country, "is_active": True}
        )
    locations: dict[str, Location] = {}
    for key, (code, name, location_type, organization_key) in LOCATION_SPECS.items():
        locations[key] = await get_or_create(
            session,
            Location,
            {"organization_id": organizations[organization_key].id, "code": code},
            {"name": name, "location_type": location_type, "is_active": True},
        )
    await session.flush()
    return organizations, locations


async def ensure_permissions(session: AsyncSession) -> dict[PermissionCode, Permission]:
    permissions: dict[PermissionCode, Permission] = {}
    for code in PermissionCode:
        permissions[code] = await get_or_create(
            session, Permission, {"code": code.value}, {"name": PERMISSION_NAMES.get(code, code.value)}
        )
    return permissions


async def ensure_roles_and_users(
    session: AsyncSession,
    organizations: dict[str, Organization],
    locations: dict[str, Location],
    permissions: dict[PermissionCode, Permission],
) -> dict[str, User]:
    # Reconcile any pre-0009 fixture rows before creating the canonical role
    # set.  This is deliberately repeated in the seed script (in addition to
    # the Alembic migration) so a developer who only runs the seed command can
    # still converge an old local database safely.
    roles: dict[str, Role] = {}
    for code, metadata in ROLE_METADATA.items():
        if code not in ROLE_DEFS:
            continue
        role = await get_or_create(
            session,
            Role,
            {"code": code},
            {
                "name": metadata.name,
                "is_active": True,
                "work_group": metadata.work_group,
                "description": metadata.description,
            },
        )
        roles[code] = role

    # The bootstrap script owns the super-admin row, but older local databases
    # may have created it before work-group metadata was introduced.  Fill the
    # descriptive fields without changing its permissions or account.
    super_admin = await session.scalar(select(Role).where(Role.code == "super_admin"))
    if super_admin is not None:
        metadata = ROLE_METADATA["super_admin"]
        super_admin.is_active = True
        super_admin.work_group = super_admin.work_group or metadata.work_group
        super_admin.description = super_admin.description or metadata.description

    # Move users off legacy role links, but retain the role rows as inactive
    # configuration history.  User records themselves are never deleted.
    for legacy_code, canonical_code in LEGACY_ROLE_TO_CANONICAL.items():
        legacy_role = await session.scalar(select(Role).where(Role.code == legacy_code))
        canonical_role = roles.get(canonical_code)
        if legacy_role is None or canonical_role is None:
            continue
        legacy_user_ids = list(await session.scalars(
            select(UserRole.user_id).where(UserRole.role_id == legacy_role.id)
        ))
        for user_id in legacy_user_ids:
            existing = await session.scalar(select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == canonical_role.id
            ))
            if existing is None:
                session.add(UserRole(user_id=user_id, role_id=canonical_role.id))
        await session.execute(delete(UserRole).where(UserRole.role_id == legacy_role.id))
        await session.execute(delete(RolePermission).where(RolePermission.role_id == legacy_role.id))
        legacy_role.is_active = False
        legacy_role.name = f"{canonical_role.name}（已合并）"
        legacy_role.work_group = f"LEGACY_{canonical_role.work_group}"
        legacy_role.description = f"历史角色，权限已合并至 {canonical_code}"

    # Reconcile canonical role permissions exactly.  This also removes stale
    # links left by an earlier version of the fixture.
    for code, (_, role_permissions) in ROLE_DEFS.items():
        role = roles[code]
        await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for permission_code in role_permissions:
            session.add(RolePermission(role_id=role.id, permission_id=permissions[permission_code].id))
    await session.flush()

    users: dict[str, User] = {}
    for username, display_name, role_code, default_location_key, overrides in USER_DEFS:
        user = await get_or_create(
            session, User, {"username": username}, {"display_name": display_name, "is_active": True}
        )
        if not user.password_hash or not verify_password(DEMO_PASSWORD, user.password_hash):
            user.password_hash = hash_password(DEMO_PASSWORD)
        user.display_name = display_name
        user.is_active = True
        users[username] = user
        await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
        await session.execute(delete(UserScope).where(UserScope.user_id == user.id))
        session.add(UserRole(user_id=user.id, role_id=roles[role_code].id))
        for permission_code in ROLE_DEFS[role_code][1]:
            raw_scope = overrides.get(permission_code, (ScopeKind.LOCATION, default_location_key))
            scope_specs = raw_scope if isinstance(raw_scope, list) else [raw_scope]
            for scope_kind, scope_key in scope_specs:
                if scope_kind == ScopeKind.ALL:
                    scope_value = None
                elif scope_kind == ScopeKind.ORGANIZATION:
                    if scope_key is None:
                        raise ValueError(f"组织范围缺少 key: {username}/{permission_code}")
                    scope_value = str(organizations[scope_key].id)
                elif scope_kind == ScopeKind.LOCATION:
                    if scope_key is None:
                        scope_kind = ScopeKind.ALL
                        scope_value = None
                    else:
                        scope_value = str(locations[scope_key].id)
                else:
                    scope_value = scope_key
                session.add(UserScope(
                    user_id=user.id,
                    permission_code=permission_code.value,
                    scope_kind=scope_kind.value,
                    scope_value=scope_value,
                ))

    # Keep the old demo usernames as inactive aliases.  Their rows and old
    # password hashes remain available for audit, but operators are directed
    # to the single canonical account for each real job.
    for legacy_username, canonical_username in LEGACY_USER_TO_CANONICAL.items():
        legacy_user = await session.scalar(select(User).where(User.username == legacy_username))
        canonical_user = users.get(canonical_username)
        if legacy_user is None or canonical_user is None:
            continue
        legacy_user.is_active = False
        suffix = f"（已合并，请使用 {canonical_username}）"
        # Rebuild the label from the original portion so repeated seed runs
        # do not accumulate nested migration suffixes.
        base_display_name = legacy_user.display_name.split("（已合并，请使用", 1)[0].rstrip()
        legacy_user.display_name = f"{base_display_name}{suffix}"
        await session.execute(delete(UserScope).where(UserScope.user_id == legacy_user.id))
        await session.execute(delete(UserRole).where(UserRole.user_id == legacy_user.id))
        # Backward-compatible internal lookup for deterministic document and
        # timeline fixtures; it points to the canonical user ID, not the
        # inactive alias, so new audit rows identify the real job account.
        users[legacy_username] = canonical_user
    await session.flush()
    return users


async def ensure_boxes_and_trays(
    session: AsyncSession, locations: dict[str, Location]
) -> tuple[dict[str, Box], dict[str, Tray]]:
    boxes: dict[str, Box] = {}
    for key, (code, location_key, seal_code) in BOX_SPECS.items():
        boxes[key] = await get_or_create(
            session,
            Box,
            {"code": code},
            {
                "current_location_id": locations[location_key].id if location_key else None,
                "seal_code": seal_code,
                "is_active": True,
            },
        )
    await session.flush()
    trays: dict[str, Tray] = {}
    for key, (code, location_key, box_key) in TRAY_SPECS.items():
        trays[key] = await get_or_create(
            session,
            Tray,
            {"code": code},
            {
                "current_location_id": locations[location_key].id if location_key else None,
                "current_box_id": boxes[box_key].id if box_key else None,
                "is_active": True,
            },
        )
    await session.flush()
    at = BASE_TIME
    for key, (_, _, box_key) in TRAY_SPECS.items():
        tray = trays[key]
        desired_box_id = boxes[box_key].id if box_key else None
        active = list(await session.scalars(select(TrayBoxRelation).where(
            TrayBoxRelation.tray_id == tray.id, TrayBoxRelation.ended_at.is_(None)
        )))
        matching: TrayBoxRelation | None = None
        for relation in active:
            if desired_box_id is not None and relation.box_id == desired_box_id and matching is None:
                matching = relation
            else:
                relation.ended_at = at
        if desired_box_id is not None and matching is None:
            session.add(TrayBoxRelation(tray_id=tray.id, box_id=desired_box_id, started_at=at))
        tray.current_box_id = desired_box_id
    await session.flush()
    return boxes, trays


async def ensure_phones(
    session: AsyncSession,
    specs: dict[int, PhoneSpec],
    organizations: dict[str, Organization],
    locations: dict[str, Location],
    trays: dict[str, Tray],
) -> dict[int, PhoneDevice]:
    phones: dict[int, PhoneDevice] = {}
    for index in sorted(specs):
        spec = specs[index]
        imei = demo_imei(index)
        imei2 = demo_imei(100 + index) if spec.imei2 else None
        phone = await session.scalar(select(PhoneDevice).where(PhoneDevice.imei == imei))
        if phone is None:
            phone = PhoneDevice(imei=imei)
            session.add(phone)
            await session.flush()
        if imei2:
            collision = await session.scalar(select(PhoneDevice).where(
                PhoneDevice.imei2 == imei2, PhoneDevice.id != phone.id
            ))
            if collision is not None:
                raise ValueError(f"演示 IMEI2 已被其他手机占用: {imei2}")
        phone.imei = imei
        phone.imei2 = imei2
        phone.brand = "Apple" if index % 2 else "Samsung"
        phone.model = "iPhone 13" if index % 2 else "Galaxy S22"
        phone.storage = "128GB" if index % 3 else "256GB"
        phone.color = "黑色" if index % 2 else "深空灰"
        phone.condition = spec.condition
        phone.battery_health = 84 + (index % 13)
        phone.purchase_price = Decimal("180.00") + Decimal(index)
        phone.status = spec.status
        phone.current_organization_id = organizations[spec.organization_key].id if spec.organization_key else None
        phone.current_location_id = locations[spec.location_key].id if spec.location_key else None
        phone.current_tray_id = trays[spec.tray_key].id if spec.tray_key else None
        phones[index] = phone
    await session.flush()

    for index, spec in specs.items():
        phone = phones[index]
        desired_tray_id = trays[spec.tray_key].id if spec.tray_key else None
        active = list(await session.scalars(select(PhoneTrayRelation).where(
            PhoneTrayRelation.phone_id == phone.id, PhoneTrayRelation.ended_at.is_(None)
        )))
        matching: PhoneTrayRelation | None = None
        for relation in active:
            if desired_tray_id is not None and relation.tray_id == desired_tray_id and matching is None:
                matching = relation
            else:
                relation.ended_at = BASE_TIME
        if desired_tray_id is not None and matching is None:
            session.add(PhoneTrayRelation(phone_id=phone.id, tray_id=desired_tray_id, started_at=BASE_TIME))
        phone.current_tray_id = desired_tray_id
    await session.flush()
    return phones


async def upsert_purchase(
    session: AsyncSession, order_no: str, organization_id: int, operator_id: int,
    phones: list[PhoneDevice],
) -> PurchaseOrder:
    order = await get_or_create(
        session, PurchaseOrder, {"order_no": order_no},
        {"organization_id": organization_id, "supplier": "演示供应商·深圳收购批次",
         "status": DocumentStatus.COMPLETED.value, "operator_id": operator_id,
         "total_count": len(phones), "note": "演示：收购→验收→后续跨境流转"},
    )
    order.total_count = len(phones)
    for phone in phones:
        item = await get_or_create(session, PurchaseItem,
                                   {"purchase_order_id": order.id, "phone_id": phone.id},
                                   {"purchase_price": phone.purchase_price})
        item.purchase_price = phone.purchase_price
    await session.flush()
    return order


async def upsert_shipment(
    session: AsyncSession, shipment_no: str, origin_org: int, origin_loc: int,
    destination_org: int, destination_loc: int, status: DocumentStatus,
    logistics_no: str, operator_id: int, phone_indexes: list[int],
    phones: dict[int, PhoneDevice], source_tray_id: int | None,
    source_box_id: int | None, container_code: str,
) -> Shipment:
    shipment = await get_or_create(
        session, Shipment, {"shipment_no": shipment_no},
        {"origin_organization_id": origin_org, "origin_location_id": origin_loc,
         "destination_organization_id": destination_org, "destination_location_id": destination_loc,
         "status": status.value, "logistics_no": logistics_no, "operator_id": operator_id,
         "total_count": len(phone_indexes)},
    )
    shipment.total_count = len(phone_indexes)
    await get_or_create(session, ShipmentContainer,
                        {"shipment_id": shipment.id, "container_kind": ContainerKind.BOX.value,
                         "container_code": container_code})
    for index in phone_indexes:
        phone = phones[index]
        item = await get_or_create(
            session, ShipmentItem, {"shipment_id": shipment.id, "phone_id": phone.id},
            {"imei_snapshot": phone.imei, "source_tray_id": source_tray_id, "source_box_id": source_box_id},
        )
        item.imei_snapshot = phone.imei
        item.source_tray_id = source_tray_id
        item.source_box_id = source_box_id
    await session.flush()
    return shipment


async def upsert_receiving(
    session: AsyncSession, receiving_no: str, shipment: Shipment, organization_id: int,
    location_id: int, status: DocumentStatus, operator_id: int, phone_indexes: list[int],
    phones: dict[int, PhoneDevice], accepted_count: int, exception_count: int,
) -> ReceivingOrder:
    order = await get_or_create(
        session, ReceivingOrder, {"receiving_no": receiving_no},
        {"shipment_id": shipment.id, "organization_id": organization_id, "location_id": location_id,
         "status": status.value, "operator_id": operator_id, "expected_count": len(phone_indexes),
         "accepted_count": accepted_count, "exception_count": exception_count},
    )
    order.expected_count = len(phone_indexes)
    order.accepted_count = accepted_count
    order.exception_count = exception_count
    for index in phone_indexes:
        result = "ACCEPTED" if status == DocumentStatus.COMPLETED else None
        item = await get_or_create(session, ReceivingItem,
                                   {"receiving_order_id": order.id, "phone_id": phones[index].id},
                                   {"imei_snapshot": phones[index].imei, "result": result})
        item.imei_snapshot = phones[index].imei
        item.result = result
        item.checked_at = BASE_TIME + timedelta(minutes=5) if result else None
    await session.flush()
    return order


async def upsert_transfer(
    session: AsyncSession, transfer_no: str, source_org: int, source_loc: int,
    destination_org: int, destination_loc: int, status: DocumentStatus,
    operator_id: int, phone_indexes: list[int], phones: dict[int, PhoneDevice],
    container_kind: ContainerKind, container_code: str, source_tray_id: int | None = None,
    source_box_id: int | None = None, received_count: int = 0,
) -> TransferOrder:
    order = await get_or_create(
        session, TransferOrder, {"transfer_no": transfer_no},
        {"source_organization_id": source_org, "source_location_id": source_loc,
         "destination_organization_id": destination_org, "destination_location_id": destination_loc,
         "status": status.value, "operator_id": operator_id, "total_count": len(phone_indexes),
         "received_count": received_count, "exception_count": 0},
    )
    order.total_count = len(phone_indexes)
    order.received_count = received_count
    await get_or_create(session, TransferContainer,
                        {"transfer_order_id": order.id, "container_kind": container_kind.value,
                         "container_code": container_code})
    for index in phone_indexes:
        received_at = BASE_TIME + timedelta(minutes=20) if received_count else None
        item = await get_or_create(
            session, TransferItem, {"transfer_order_id": order.id, "phone_id": phones[index].id},
            {"imei_snapshot": phones[index].imei, "source_tray_id": source_tray_id,
             "source_box_id": source_box_id, "received_at": received_at},
        )
        item.imei_snapshot = phones[index].imei
        item.source_tray_id = source_tray_id
        item.source_box_id = source_box_id
        item.received_at = received_at
    await session.flush()
    return order


async def upsert_sale(
    session: AsyncSession, sales_no: str, organization_id: int, location_id: int,
    status: DocumentStatus, operator_id: int, approver_id: int | None, index: int,
    phones: dict[int, PhoneDevice], price: Decimal, customer: str,
    source_tray_id: int | None,
) -> SalesOrder:
    order = await get_or_create(
        session, SalesOrder, {"sales_no": sales_no},
        {"organization_id": organization_id, "location_id": location_id, "sales_type": "RETAIL",
         "status": status.value, "customer_name": customer, "total_count": 1,
         "total_amount": price, "operator_id": operator_id, "approver_id": approver_id,
         "note": "演示：门店逐台销售与审核"},
    )
    order.organization_id = organization_id
    order.location_id = location_id
    order.status = status.value
    order.total_count = 1
    order.total_amount = price
    order.operator_id = operator_id
    order.approver_id = approver_id
    phone = phones[index]
    await get_or_create(session, SalesContainer,
                        {"sales_order_id": order.id, "container_kind": ContainerKind.PHONE.value,
                         "container_code": phone.imei})
    item = await get_or_create(
        session, SalesItem, {"sales_order_id": order.id, "phone_id": phone.id},
        {"imei_snapshot": phone.imei, "sale_price": price, "source_tray_id": source_tray_id,
         "source_box_id": None},
    )
    item.imei_snapshot = phone.imei
    item.sale_price = price
    item.source_tray_id = source_tray_id
    await session.flush()
    return order


async def upsert_return(
    session: AsyncSession, return_no: str, sales_order: SalesOrder, source_org: int,
    source_loc: int, destination_org: int, destination_loc: int, status: DocumentStatus,
    operator_id: int, index: int, phones: dict[int, PhoneDevice], container_code: str,
    received: bool,
) -> ReturnOrder:
    order = await get_or_create(
        session, ReturnOrder, {"return_no": return_no},
        {"sales_order_id": sales_order.id, "source_organization_id": source_org,
         "source_location_id": source_loc, "destination_organization_id": destination_org,
         "destination_location_id": destination_loc, "status": status.value, "total_count": 1,
         "operator_id": operator_id, "received_count": 1 if received else 0,
         "note": "演示：门店退回管理处验收"},
    )
    # Keep an existing demo row convergent when the physical destination or
    # status changes between fixture revisions.  ``get_or_create`` only
    # applies these values on insert, which would otherwise leave a previously
    # seeded return pointing at the repair area instead of the management
    # office receiving zone.
    order.sales_order_id = sales_order.id
    order.source_organization_id = source_org
    order.source_location_id = source_loc
    order.destination_organization_id = destination_org
    order.destination_location_id = destination_loc
    order.status = status.value
    order.total_count = 1
    order.operator_id = operator_id
    order.received_count = 1 if received else 0
    # A deterministic demo return has one physical source container.  Remove
    # rows left by an earlier fixture revision (for example a temporary repair
    # tray) so rerunning the seed converges instead of accumulating stale
    # container snapshots under the same return number.
    existing_containers = list(await session.scalars(
        select(ReturnContainer).where(ReturnContainer.return_order_id == order.id)
    ))
    for existing in existing_containers:
        if existing.container_kind != ContainerKind.BOX.value or existing.container_code != container_code:
            await session.delete(existing)
    phone = phones[index]
    await get_or_create(session, ReturnContainer,
                        {"return_order_id": order.id, "container_kind": ContainerKind.BOX.value,
                         "container_code": container_code})
    # The fixture models one returned phone per return order.  If an older
    # version used a different phone, drop that stale child row before
    # upserting the current snapshot.
    existing_items = list(await session.scalars(
        select(ReturnItem).where(ReturnItem.return_order_id == order.id)
    ))
    for existing in existing_items:
        if existing.phone_id != phones[index].id:
            await session.delete(existing)
    item = await get_or_create(
        session, ReturnItem, {"return_order_id": order.id, "phone_id": phone.id},
        {"imei_snapshot": phone.imei, "received_at": BASE_TIME + timedelta(hours=2) if received else None},
    )
    item.imei_snapshot = phone.imei
    item.received_at = BASE_TIME + timedelta(hours=2) if received else None
    await session.flush()
    return order


async def upsert_repair(
    session: AsyncSession, repair_no: str, return_order: ReturnOrder | None,
    organization_id: int, location_id: int, status: DocumentStatus, operator_id: int,
    technician_id: int | None, index: int, phones: dict[int, PhoneDevice], *,
    completed: bool = False, accepted: bool = False, disposition: str | None = None,
    container_code: str | None = None, accepter_id: int | None = None,
) -> RepairOrder:
    order = await get_or_create(
        session, RepairOrder, {"repair_no": repair_no},
        {"return_order_id": return_order.id if return_order else None, "organization_id": organization_id,
         "location_id": location_id, "status": status.value, "operator_id": operator_id,
         "technician_id": technician_id, "total_count": 1, "completed_count": 1 if completed else 0,
         "accepted_count": 1 if accepted else 0, "exception_count": 0,
         "note": "演示：维修接单、维修、QA验收"},
    )
    order.return_order_id = return_order.id if return_order else None
    order.organization_id = organization_id
    order.location_id = location_id
    order.status = status.value
    order.operator_id = operator_id
    order.technician_id = technician_id
    order.total_count = 1
    order.exception_count = 0
    order.completed_count = 1 if completed else 0
    order.accepted_count = 1 if accepted else 0
    # Keep this deterministic fixture's container snapshot convergent across
    # revisions.  In particular, the received return tray is the source
    # snapshot; the destination repair tray must not be attached as a second
    # container row after a rerun.
    existing_containers = list(await session.scalars(
        select(RepairContainer).where(RepairContainer.repair_order_id == order.id)
    ))
    for existing in existing_containers:
        if (
            container_code is None
            or existing.container_kind != ContainerKind.TRAY.value
            or existing.container_code != container_code
        ):
            await session.delete(existing)
    if container_code:
        await get_or_create(session, RepairContainer,
                            {"repair_order_id": order.id, "container_kind": ContainerKind.TRAY.value,
                             "container_code": container_code})
    # A completed/active single-phone repair does not need a container
    # snapshot; stale rows were removed above on every branch.
    phone = phones[index]
    existing_items = list(await session.scalars(
        select(RepairItem).where(RepairItem.repair_order_id == order.id)
    ))
    for existing in existing_items:
        if existing.phone_id != phone.id:
            await session.delete(existing)
    completed_at = BASE_TIME + timedelta(hours=3) if completed else None
    accepted_at = BASE_TIME + timedelta(hours=4) if accepted else None
    item = await get_or_create(
        session, RepairItem, {"repair_order_id": order.id, "phone_id": phone.id},
        {"imei_snapshot": phone.imei,
         "fault_description": "屏幕触控异常" if index in {44, 45, 46} else "电池健康度偏低",
         "diagnosis": "演示诊断记录" if completed else None,
         "work_done": "更换屏幕组件并复测" if completed else None,
         "parts": ["演示屏幕组件"] if completed else None,
         "repair_cost": Decimal("35.00") if completed else None,
         "repair_result": "REPAIRED" if completed else None, "completed_at": completed_at,
         "completed_by": technician_id if completed else None,
         "disposition": disposition if accepted else None, "accepted_at": accepted_at,
         "accepted_by": accepter_id if accepted else None},
    )
    item.imei_snapshot = phone.imei
    item.fault_description = "屏幕触控异常" if index in {44, 45, 46} else "电池健康度偏低"
    item.diagnosis = "演示诊断记录" if completed else None
    item.work_done = "更换屏幕组件并复测" if completed else None
    item.parts = ["演示屏幕组件"] if completed else None
    item.repair_cost = Decimal("35.00") if completed else None
    item.repair_result = "REPAIRED" if completed else None
    item.completed_at = completed_at
    item.completed_by = technician_id if completed else None
    item.accepted_at = accepted_at
    item.accepted_by = accepter_id if accepted else None
    item.disposition = disposition if accepted else None
    await session.flush()
    return order


async def upsert_stocktakes(
    session: AsyncSession, organization_id: int, store_a_id: int, store_b_id: int,
    operator_id: int, reviewer_id: int, phones: dict[int, PhoneDevice],
) -> tuple[StocktakeOrder, StocktakeOrder]:
    clean_phones = [phones[index] for index in (39, 40, 41, 52)]
    clean = await get_or_create(
        session, StocktakeOrder, {"stocktake_no": f"{DEMO_PREFIX}ST-STORE-A-CLEAN"},
        {"organization_id": organization_id, "location_id": store_a_id, "status": DocumentStatus.COMPLETED.value,
         "operator_id": operator_id, "expected_count": len(clean_phones), "found_count": len(clean_phones),
         "missing_count": 0, "extra_count": 0, "adjustment_status": "COMPLETED", "reviewer_id": reviewer_id,
         "reviewed_at": BASE_TIME + timedelta(hours=5), "note": "演示：门店A完整盘点"},
    )
    clean.expected_count = clean.found_count = len(clean_phones)
    clean.missing_count = clean.extra_count = 0
    clean.adjustment_status = "COMPLETED"
    for phone in clean_phones:
        await get_or_create(session, StocktakeItem,
                            {"stocktake_order_id": clean.id, "imei_snapshot": phone.imei},
                            {"phone_id": phone.id, "result": "FOUND", "scanned_at": BASE_TIME + timedelta(hours=5)})

    extra_imei = demo_imei(900)
    difference = await get_or_create(
        session, StocktakeOrder, {"stocktake_no": f"{DEMO_PREFIX}ST-STORE-B-DIFF"},
        {"organization_id": organization_id, "location_id": store_b_id, "status": DocumentStatus.COMPLETED.value,
         "operator_id": operator_id, "expected_count": 1, "found_count": 1, "missing_count": 0,
         "extra_count": 1, "adjustment_status": "OPEN", "note": "演示：门店B发现一台未建档手机，等待主管处理"},
    )
    difference.expected_count = difference.found_count = 1
    difference.missing_count = 0
    difference.extra_count = 1
    difference.adjustment_status = "OPEN"
    await get_or_create(session, StocktakeItem,
                        {"stocktake_order_id": difference.id, "imei_snapshot": phones[50].imei},
                        {"phone_id": phones[50].id, "result": "FOUND", "scanned_at": BASE_TIME + timedelta(hours=6)})
    await get_or_create(session, StocktakeItem,
                        {"stocktake_order_id": difference.id, "imei_snapshot": extra_imei},
                        {"phone_id": None, "result": "EXTRA", "scanned_at": BASE_TIME + timedelta(hours=6)})
    await session.flush()
    return clean, difference


async def seed_documents(
    session: AsyncSession, organizations: dict[str, Organization], locations: dict[str, Location],
    boxes: dict[str, Box], trays: dict[str, Tray], phones: dict[int, PhoneDevice], users: dict[str, User],
) -> dict[str, Any]:
    """Create all orders, containers and item snapshots used by the demo."""

    sz_id, gh_id = organizations["sz"].id, organizations["gh"].id
    sz_wh_id, gh_mgmt_id = locations["sz_wh"].id, locations["gh_mgmt"].id
    store_a_id, store_b_id, repair_id = locations["store_a"].id, locations["store_b"].id, locations["repair"].id

    po1 = await upsert_purchase(session, f"{DEMO_PREFIX}PO-SZ-001", sz_id, users["szops"].id, [phones[i] for i in range(1, 25)])
    po2 = await upsert_purchase(session, f"{DEMO_PREFIX}PO-SZ-002", sz_id, users["szops"].id, [phones[i] for i in range(25, 53)])
    ship_ready = await upsert_shipment(session, f"{DEMO_PREFIX}SHIP-SZ-GH-READY", sz_id, sz_wh_id, gh_id, gh_mgmt_id, DocumentStatus.IN_TRANSIT, "DEMO-AIR-READY-001", users["szdispatch"].id, list(range(17, 21)), phones, trays["sz_inbound"].id, boxes["sz_inbound"].id, boxes["sz_inbound"].code)
    ship_checking = await upsert_shipment(session, f"{DEMO_PREFIX}SHIP-SZ-GH-CHECKING", sz_id, sz_wh_id, gh_id, gh_mgmt_id, DocumentStatus.RECEIVING, "DEMO-SEA-CHECK-002", users["szdispatch"].id, list(range(21, 25)), phones, trays["sz_checking"].id, boxes["sz_checking"].id, boxes["sz_checking"].code)
    ship_history = await upsert_shipment(session, f"{DEMO_PREFIX}SHIP-SZ-GH-HISTORY", sz_id, sz_wh_id, gh_id, gh_mgmt_id, DocumentStatus.COMPLETED, "DEMO-SEA-HISTORY-003", users["szdispatch"].id, list(range(25, 35)), phones, trays["sz_history"].id, boxes["sz_history"].id, boxes["sz_history"].code)
    rcv_checking = await upsert_receiving(session, f"{DEMO_PREFIX}RCV-GH-CHECKING", ship_checking, gh_id, gh_mgmt_id, DocumentStatus.RECEIVING, users["ghops"].id, list(range(21, 25)), phones, 0, 0)
    rcv_history = await upsert_receiving(session, f"{DEMO_PREFIX}RCV-GH-HISTORY", ship_history, gh_id, gh_mgmt_id, DocumentStatus.COMPLETED, users["ghops"].id, list(range(25, 35)), phones, 10, 0)
    transfer_ready = await upsert_transfer(session, f"{DEMO_PREFIX}TRF-GH-STORE-A-READY", gh_id, gh_mgmt_id, gh_id, store_a_id, DocumentStatus.IN_TRANSIT, users["ghops"].id, list(range(35, 39)), phones, ContainerKind.BOX, boxes["to_store_a"].code, trays["to_store_a"].id, boxes["to_store_a"].id)
    transfer_history_a = await upsert_transfer(session, f"{DEMO_PREFIX}TRF-GH-STORE-A-HISTORY", gh_id, gh_mgmt_id, gh_id, store_a_id, DocumentStatus.COMPLETED, users["ghops"].id, list(range(39, 45)), phones, ContainerKind.TRAY, trays["store_a"].code, trays["gh_available"].id, boxes["gh_available"].id, 6)
    transfer_history_b = await upsert_transfer(session, f"{DEMO_PREFIX}TRF-GH-STORE-B-HISTORY", gh_id, gh_mgmt_id, gh_id, store_b_id, DocumentStatus.COMPLETED, users["ghops"].id, [50], phones, ContainerKind.TRAY, trays["store_b"].code, trays["gh_available"].id, boxes["gh_available"].id, 1)
    transfer_store_a_b = await upsert_transfer(session, f"{DEMO_PREFIX}TRF-STORE-A-B-READY", gh_id, store_a_id, gh_id, store_b_id, DocumentStatus.IN_TRANSIT, users["storeasupervisor"].id, [51], phones, ContainerKind.PHONE, phones[51].imei)
    sale_pending = await upsert_sale(session, f"{DEMO_PREFIX}SALE-STORE-A-PENDING", gh_id, store_a_id, DocumentStatus.PENDING_CONFIRMATION, users["storeaclerk"].id, None, 41, phones, Decimal("299.00"), "演示客户 A", trays["store_a"].id)
    sale_done = await upsert_sale(session, f"{DEMO_PREFIX}SALE-STORE-A-DONE", gh_id, store_a_id, DocumentStatus.COMPLETED, users["storeaclerk"].id, users["storeasupervisor"].id, 42, phones, Decimal("280.00"), "演示批发客户", None)
    sale_return_transit = await upsert_sale(session, f"{DEMO_PREFIX}SALE-STORE-A-RETURN-TRANSIT", gh_id, store_a_id, DocumentStatus.COMPLETED, users["storeaclerk"].id, users["storeasupervisor"].id, 43, phones, Decimal("265.00"), "演示退货客户 A", trays["store_a"].id)
    sale_return_received = await upsert_sale(session, f"{DEMO_PREFIX}SALE-STORE-A-RETURN-RECEIVED", gh_id, store_a_id, DocumentStatus.COMPLETED, users["storeaclerk"].id, users["storeasupervisor"].id, 44, phones, Decimal("255.00"), "演示退货客户 B", trays["store_a"].id)
    # The completed return is received at the management office first.  The
    # repair order records the source tray that was opened; the phones are
    # then represented in the dedicated repair-area tray.
    return_transit = await upsert_return(session, f"{DEMO_PREFIX}RET-STORE-A-TRANSIT", sale_return_transit, gh_id, store_a_id, gh_id, gh_mgmt_id, DocumentStatus.IN_TRANSIT, users["returnpack"].id, 43, phones, boxes["return_transit"].code, False)
    return_received = await upsert_return(session, f"{DEMO_PREFIX}RET-STORE-A-RECEIVED", sale_return_received, gh_id, store_a_id, gh_id, gh_mgmt_id, DocumentStatus.COMPLETED, users["returnpack"].id, 44, phones, boxes["return_received"].code, True)
    repair_submitted = await upsert_repair(session, f"{DEMO_PREFIX}REP-SUBMITTED", return_received, gh_id, repair_id, DocumentStatus.SUBMITTED, users["ghops"].id, None, 44, phones, container_code=trays["return_received"].code)
    repair_active = await upsert_repair(session, f"{DEMO_PREFIX}REP-ACTIVE", None, gh_id, repair_id, DocumentStatus.IN_PROGRESS, users["ghops"].id, users["repairtech"].id, 45, phones)
    repair_qa = await upsert_repair(session, f"{DEMO_PREFIX}REP-QA", None, gh_id, repair_id, DocumentStatus.PENDING_ACCEPTANCE, users["ghops"].id, users["repairtech"].id, 46, phones, completed=True)
    repair_done = await upsert_repair(session, f"{DEMO_PREFIX}REP-DONE", None, gh_id, repair_id, DocumentStatus.COMPLETED, users["ghops"].id, users["repairtech"].id, 47, phones, completed=True, accepted=True, disposition="AVAILABLE_AGAIN", accepter_id=users["ghops"].id)
    stocktake_clean, stocktake_difference = await upsert_stocktakes(session, gh_id, store_a_id, store_b_id, users["storeaclerk"].id, users["storeasupervisor"].id, phones)
    await session.flush()
    return locals()


def event(index: int, slug: str, action: str, from_status: PhoneStatus | None, to_status: PhoneStatus, *, from_location_id: int | None = None, to_location_id: int | None = None, from_tray_id: int | None = None, to_tray_id: int | None = None, from_box_id: int | None = None, to_box_id: int | None = None, document_type: str | None = None, document_id: str | None = None, operator_id: int | None = None, note: str | None = None) -> dict[str, Any]:
    return {"index": index, "key": f"{DEMO_PREFIX.lower()}phone:{index:02d}:{slug}", "action": action, "from_status": from_status.value if from_status else None, "to_status": to_status.value, "from_location_id": from_location_id, "to_location_id": to_location_id, "from_tray_id": from_tray_id, "to_tray_id": to_tray_id, "from_box_id": from_box_id, "to_box_id": to_box_id, "document_type": document_type, "document_id": document_id, "operator_id": operator_id, "note": note}


async def upsert_transaction(session: AsyncSession, data: dict[str, Any]) -> InventoryTransaction:
    tx = await session.scalar(select(InventoryTransaction).where(InventoryTransaction.idempotency_key == data["key"]))
    values = {key: value for key, value in data.items() if key not in {"index", "key"}}
    values["idempotency_key"] = data["key"]
    if tx is None:
        tx = InventoryTransaction(**values)
        session.add(tx)
    else:
        for key, value in values.items():
            setattr(tx, key, value)
    await session.flush()
    return tx


async def seed_transactions(
    session: AsyncSession, specs: dict[int, PhoneSpec], phones: dict[int, PhoneDevice],
    locations: dict[str, Location], boxes: dict[str, Box], trays: dict[str, Tray], users: dict[str, User],
) -> None:
    """Write a realistic status/location/container timeline for each phone."""

    sz, gh = locations["sz_wh"].id, locations["gh_mgmt"].id
    store_a, store_b, repair = locations["store_a"].id, locations["store_b"].id, locations["repair"].id
    for index in sorted(specs):
        phone = phones[index]
        events: list[dict[str, Any]] = []

        def add_event(*args: Any, **kwargs: Any) -> None:
            item = event(index, *args, **kwargs)
            item["phone_id"] = phone.id
            events.append(item)

        purchase_no = f"{DEMO_PREFIX}PO-SZ-001" if index <= 24 else f"{DEMO_PREFIX}PO-SZ-002"
        add_event("purchase", "采购入库", None, PhoneStatus.SHENZHEN_STOCK, to_location_id=sz, document_type="purchase", document_id=purchase_no, operator_id=users["szops"].id)
        state, loc, tray_id, box_id = PhoneStatus.SHENZHEN_STOCK, sz, None, None

        def move(slug: str, action: str, new_state: PhoneStatus, *, new_loc: int | None = None, new_tray: int | None = None, new_box: int | None = None, doc_type: str | None = None, doc_id: str | None = None, operator: int | None = None, note: str | None = None) -> None:
            nonlocal state, loc, tray_id, box_id
            add_event(slug, action, state, new_state, from_location_id=loc, to_location_id=new_loc, from_tray_id=tray_id, to_tray_id=new_tray, from_box_id=box_id, to_box_id=new_box, document_type=doc_type, document_id=doc_id, operator_id=operator, note=note)
            state, loc, tray_id, box_id = new_state, new_loc, new_tray, new_box

        # Shenzhen packing path.  Cross-border phones use a historical source
        # tray/box snapshot; 17-20 remain physically in the inbound box.
        if index >= 7:
            source_tray_key = "sz_open" if index in range(7, 11) else ("sz_box_a" if index in range(11, 14) else ("sz_box_b" if index in range(14, 17) else ("sz_inbound" if index in range(17, 21) else "sz_history")))
            source_tray = trays[source_tray_key].id
            move("tray", "装入托盘", PhoneStatus.IN_TRAY, new_loc=sz, new_tray=source_tray, operator=users["szops"].id, note="扫描托盘编码后连续录入 IMEI")
            if index >= 11:
                source_box_key = "sz_ready" if index in range(11, 17) else ("sz_inbound" if index in range(17, 21) else "sz_history")
                move("box", "装入箱子", PhoneStatus.IN_BOX, new_loc=sz, new_tray=source_tray, new_box=boxes[source_box_key].id, operator=users["szops"].id)

        if index >= 17:
            ship_no = f"{DEMO_PREFIX}SHIP-SZ-GH-READY" if index in range(17, 21) else (f"{DEMO_PREFIX}SHIP-SZ-GH-CHECKING" if index in range(21, 25) else f"{DEMO_PREFIX}SHIP-SZ-GH-HISTORY")
            # A box/tray remains a physical containment relation while the
            # shipment is in transit.  Receiving/unpacking events explicitly
            # clear it later.
            move("ship", "深圳发运", PhoneStatus.IN_TRANSIT, new_loc=None, new_tray=tray_id, new_box=box_id, doc_type="shipment", doc_id=ship_no, operator=users["szdispatch"].id)
            if index in range(21, 25):
                move("arrival", "加纳到货待验收", PhoneStatus.GHANA_PENDING_INSPECTION, new_loc=gh, new_tray=None, new_box=None, doc_type="receiving", doc_id=f"{DEMO_PREFIX}RCV-GH-CHECKING", operator=users["ghops"].id)
            elif index >= 25:
                final_tray = trays[specs[index].tray_key].id if specs[index].tray_key else None
                final_box = None
                if specs[index].tray_key:
                    _, _, box_key = TRAY_SPECS[specs[index].tray_key]
                    final_box = boxes[box_key].id if box_key else None
                move("arrival", "加纳到货待验收", PhoneStatus.GHANA_PENDING_INSPECTION, new_loc=gh, new_tray=None, new_box=None, doc_type="receiving", doc_id=f"{DEMO_PREFIX}RCV-GH-HISTORY", operator=users["ghops"].id)
                move("accept", "加纳逐台验收通过", PhoneStatus.GHANA_STOCK, new_loc=gh, new_tray=final_tray, new_box=final_box, doc_type="receiving", doc_id=f"{DEMO_PREFIX}RCV-GH-HISTORY", operator=users["ghops"].id)

        if index in range(35, 39):
            move("transfer_out", "管理处调拨出库", PhoneStatus.TRANSFERRING, new_loc=None, new_tray=trays["to_store_a"].id, new_box=boxes["to_store_a"].id, doc_type="transfer", doc_id=f"{DEMO_PREFIX}TRF-GH-STORE-A-READY", operator=users["ghops"].id)
        elif index in range(39, 45) or index in {50, 51, 52}:
            target_location = store_b if index == 50 else store_a
            target_tray = trays["store_b"].id if index == 50 else (trays["store_a"].id if index in range(39, 42) else None)
            target_box = boxes["store_b"].id if index == 50 else None
            history_doc = f"{DEMO_PREFIX}TRF-GH-STORE-B-HISTORY" if index == 50 else f"{DEMO_PREFIX}TRF-GH-STORE-A-HISTORY"
            move("transfer_out", "管理处调拨出库", PhoneStatus.TRANSFERRING, new_loc=None, new_tray=None, new_box=None, doc_type="transfer", doc_id=history_doc, operator=users["ghops"].id)
            move("transfer_receive", "门店调拨收货", PhoneStatus.STORE_STOCK, new_loc=target_location, new_tray=target_tray, new_box=target_box, doc_type="transfer", doc_id=history_doc, operator=users["storeboperator"].id if index == 50 else users["storeareceive"].id)

        if index == 41:
            move("sale_pending", "销售待确认", PhoneStatus.SALE_PENDING, new_loc=store_a, new_tray=trays["store_a"].id, doc_type="sales", doc_id=f"{DEMO_PREFIX}SALE-STORE-A-PENDING", operator=users["storeaclerk"].id)
        elif index == 42:
            move("sale_pending", "销售待确认", PhoneStatus.SALE_PENDING, new_loc=store_a, doc_type="sales", doc_id=f"{DEMO_PREFIX}SALE-STORE-A-DONE", operator=users["storeaclerk"].id)
            move("sale_confirm", "销售确认", PhoneStatus.SOLD, new_loc=None, doc_type="sales", doc_id=f"{DEMO_PREFIX}SALE-STORE-A-DONE", operator=users["storeasupervisor"].id)
        elif index in {43, 44}:
            sale_no = f"{DEMO_PREFIX}SALE-STORE-A-RETURN-TRANSIT" if index == 43 else f"{DEMO_PREFIX}SALE-STORE-A-RETURN-RECEIVED"
            ret_no = f"{DEMO_PREFIX}RET-STORE-A-TRANSIT" if index == 43 else f"{DEMO_PREFIX}RET-STORE-A-RECEIVED"
            move("sale_pending", "销售待确认", PhoneStatus.SALE_PENDING, new_loc=store_a, doc_type="sales", doc_id=sale_no, operator=users["storeaclerk"].id)
            move("sale_confirm", "销售确认", PhoneStatus.SOLD, new_loc=None, doc_type="sales", doc_id=sale_no, operator=users["storeasupervisor"].id)
            move("return_dispatch", "门店退回发运", PhoneStatus.RETURN_PENDING_CHECK, new_loc=None, new_tray=trays["return_transit"].id if index == 43 else None, new_box=boxes["return_transit"].id if index == 43 else None, doc_type="return", doc_id=ret_no, operator=users["returnpack"].id)
            if index == 44:
                move("return_receive", "管理处接收销售退回", PhoneStatus.WAITING_REPAIR, new_loc=gh, new_tray=trays["return_received"].id, new_box=boxes["return_received"].id, doc_type="return", doc_id=ret_no, operator=users["ghops"].id)
                move("return_untray", "退回分诊拆托", PhoneStatus.WAITING_REPAIR, new_loc=gh, new_tray=None, new_box=None, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-SUBMITTED", operator=users["ghops"].id, note="管理处开箱、开托，逐台取出")
                move("return_triage", "退回分诊送维修", PhoneStatus.WAITING_REPAIR, new_loc=repair, new_tray=trays["repair"].id, new_box=boxes["repair"].id, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-SUBMITTED", operator=users["ghops"].id, note="管理处逐台验收后转入维修区")
        elif index == 45:
            move("repair_accept", "维修人员接收", PhoneStatus.REPAIRING, new_loc=repair, new_tray=trays["repair"].id, new_box=boxes["repair"].id, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-ACTIVE", operator=users["repairtech"].id)
        elif index == 46:
            move("repair_accept", "维修人员接收", PhoneStatus.REPAIRING, new_loc=repair, new_tray=trays["repair"].id, new_box=boxes["repair"].id, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-QA", operator=users["repairtech"].id)
            move("repair_complete", "维修完成待验收", PhoneStatus.REPAIR_PENDING_ACCEPTANCE, new_loc=repair, new_tray=trays["repair"].id, new_box=boxes["repair"].id, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-QA", operator=users["repairtech"].id)
        elif index == 47:
            move("repair_accept", "维修人员接收", PhoneStatus.REPAIRING, new_loc=repair, new_tray=trays["repair"].id, new_box=boxes["repair"].id, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-DONE", operator=users["repairtech"].id)
            move("repair_complete", "维修完成待验收", PhoneStatus.REPAIR_PENDING_ACCEPTANCE, new_loc=repair, new_tray=trays["repair"].id, new_box=boxes["repair"].id, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-DONE", operator=users["repairtech"].id)
            move("repair_review", "维修结果验收", PhoneStatus.AVAILABLE_AGAIN, new_loc=gh, new_tray=None, new_box=None, doc_type="repair", doc_id=f"{DEMO_PREFIX}REP-DONE", operator=users["ghops"].id)
        elif index == 48:
            move("freeze", "异常冻结待核查", PhoneStatus.FROZEN, new_loc=gh, doc_type="exception", doc_id=f"{DEMO_PREFIX}EXCEPTION-048", operator=users["ghops"].id, note="外观损坏待复核")
        elif index == 49:
            move("scrap", "报损/遗失登记", PhoneStatus.LOST_OR_SCRAPPED, new_loc=None, doc_type="exception", doc_id=f"{DEMO_PREFIX}EXCEPTION-049", operator=users["ghops"].id, note="演示报损样本")
        elif index == 51:
            move("store_a_to_b", "店间调拨出库", PhoneStatus.TRANSFERRING, new_loc=None, doc_type="transfer", doc_id=f"{DEMO_PREFIX}TRF-STORE-A-B-READY", operator=users["storeasupervisor"].id)

        # Reconcile timestamps as well as payloads.  Earlier fixture revisions
        # may already have an event row with a lower auto-increment id; if its
        # timestamp is left untouched, a newly added intermediate step (such
        # as "拆托" before "送维修") would appear in the wrong order in the
        # phone timeline.  The per-phone sequence is deterministic and is
        # only used for this DEMO2 snapshot.
        for position, item in enumerate(events):
            item["created_at"] = BASE_TIME + timedelta(minutes=position)
            await upsert_transaction(session, item)
    await session.flush()


async def attach_relation_sources(session: AsyncSession) -> None:
    """Link active physical relations to their deterministic transaction keys."""

    for relation in await session.scalars(select(PhoneTrayRelation).where(PhoneTrayRelation.ended_at.is_(None))):
        phone = await session.get(PhoneDevice, relation.phone_id)
        if phone is None:
            continue
        try:
            index = int(phone.imei[10:14])
        except (TypeError, ValueError):
            continue
        tx = await session.scalar(select(InventoryTransaction).where(
            InventoryTransaction.phone_id == phone.id,
            InventoryTransaction.idempotency_key == f"{DEMO_PREFIX.lower()}phone:{index:02d}:tray",
        ))
        if tx:
            relation.source_transaction_id = tx.id
    for relation in await session.scalars(select(TrayBoxRelation).where(TrayBoxRelation.ended_at.is_(None))):
        tx = await session.scalar(select(InventoryTransaction).where(
            InventoryTransaction.to_tray_id == relation.tray_id,
            InventoryTransaction.to_box_id == relation.box_id,
            InventoryTransaction.idempotency_key.like(f"{DEMO_PREFIX.lower()}phone:%:box"),
        ))
        if tx:
            relation.source_transaction_id = tx.id


async def seed(database_url: str = settings.database_url) -> None:
    if not DEMO_PASSWORD:
        raise ValueError("GHANA_DEMO_PASSWORD 不能为空")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            async with session.begin():
                organizations, locations = await ensure_organizations_and_locations(session)
                permissions = await ensure_permissions(session)
                users = await ensure_roles_and_users(session, organizations, locations, permissions)
                boxes, trays = await ensure_boxes_and_trays(session, locations)
                specs = build_phone_specs()
                phones = await ensure_phones(session, specs, organizations, locations, trays)
                documents = await seed_documents(session, organizations, locations, boxes, trays, phones, users)
                await seed_transactions(session, specs, phones, locations, boxes, trays, users)
                await attach_relation_sources(session)
            print(f"演示数据已完成（可重复执行）：{len(phones)} 台手机、{len(trays)} 个托盘、{len(boxes)} 个箱子、{len(USER_DEFS)} 个岗位账号。")
            print("所有演示账号密码均为用户指定的本地演示密码；仅用于开发环境。")
            key_rows = [documents["ship_ready"], documents["transfer_ready"], documents["sale_pending"], documents["return_transit"], documents["repair_qa"], documents["stocktake_difference"]]
            print("关键单据：", ", ".join(next(getattr(row, attr) for attr in ("order_no", "shipment_no", "transfer_no", "sales_no", "return_no", "repair_no", "stocktake_no") if hasattr(row, attr)) for row in key_rows))
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed coherent local Ghana phone-management demo data")
    parser.add_argument("--database-url", default=settings.database_url, help="SQLAlchemy async database URL")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(seed(args.database_url))
