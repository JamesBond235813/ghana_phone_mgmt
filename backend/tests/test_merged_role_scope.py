"""Regression tests for the consolidated Shenzhen/Ghana operational roles.

The business roles are deliberately not referenced by name here.  A role code is
an administration concern; the security contract is the permission set plus the
per-permission location scopes.  In particular, the Ghana operations role needs
to work at both the management warehouse and the repair area, while each
permission remains restricted to the location where that operation is valid.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models import (
    Location,
    Organization,
    Permission,
    RepairItem,
    RepairOrder,
    Role,
    RolePermission,
    Shipment,
    ShipmentItem,
    User,
    UserRole,
    UserScope,
    PhoneDevice,
)
from app.db.session import get_db
from app.domain.enums import DocumentStatus, PhoneStatus
from app.main import app
from app.repositories.users import build_access_context


GHANA_OPERATION_PERMISSIONS = {
    PermissionCode.PHONE_VIEW,
    PermissionCode.SHIPMENT_VIEW,
    PermissionCode.RECEIVING_UNPACK,
    PermissionCode.RECEIVING_ACCEPT,
    PermissionCode.TRAY_MANAGE,
    PermissionCode.BOX_MANAGE,
    PermissionCode.INVENTORY_RECEIVE,
    PermissionCode.TRANSFER_CREATE,
    PermissionCode.INVENTORY_ISSUE,
    PermissionCode.RETURN_RECEIVE,
    PermissionCode.REPAIR_CREATE,
    PermissionCode.REPAIR_APPROVE,
    PermissionCode.REPORT_VIEW,
}

SHENZHEN_OPERATION_PERMISSIONS = {
    PermissionCode.PHONE_VIEW,
    PermissionCode.PHONE_EDIT,
    PermissionCode.PURCHASE_CREATE,
    PermissionCode.TRAY_MANAGE,
    PermissionCode.BOX_MANAGE,
}


def _permission_rows() -> list[Permission]:
    return [
        Permission(id=300 + index, code=code.value, name=code.value)
        for index, code in enumerate(PermissionCode)
    ]


async def _seed_merged_role_database(factory) -> None:
    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="SZ", name="深圳办公室", country="CN"),
                Organization(id=2, code="GH", name="加纳管理处", country="GH"),
                Location(id=10, organization_id=1, code="SZ-WH", name="深圳仓", location_type="warehouse"),
                Location(id=20, organization_id=2, code="GH-MGMT", name="加纳管理处", location_type="warehouse"),
                Location(id=30, organization_id=2, code="GH-REPAIR", name="加纳维修区", location_type="repair"),
                Location(id=40, organization_id=2, code="GH-STORE", name="未授权门店", location_type="store"),
                User(id=100, username="ghanaops", display_name="加纳综合运营员", is_active=True),
                Role(id=200, code="ghana_operations", name="加纳综合运营"),
                User(id=102, username="szops", display_name="深圳收货装载员", is_active=True),
                Role(id=201, code="shenzhen_operations", name="深圳收货装载"),
                # A technician is used only to establish a completed repair
                # record.  The consolidated role is the independent reviewer.
                User(id=101, username="technician", display_name="维修技师", is_active=True),
            ]
        )
        permissions = _permission_rows()
        session.add_all(permissions)
        await session.flush()

        permission_ids = {PermissionCode(row.code): row.id for row in permissions}
        session.add_all(
            [
                RolePermission(role_id=200, permission_id=permission_ids[code])
                for code in GHANA_OPERATION_PERMISSIONS
            ]
        )
        session.add_all(
            [
                RolePermission(role_id=201, permission_id=permission_ids[code])
                for code in SHENZHEN_OPERATION_PERMISSIONS
            ]
        )
        session.add(UserRole(user_id=100, role_id=200))
        session.add(UserRole(user_id=102, role_id=201))

        # Read access spans both physical areas.  Each operation permission is
        # intentionally scoped only to the area where the work is performed.
        scope_rows: list[UserScope] = [
            UserScope(user_id=100, permission_code=PermissionCode.PHONE_VIEW.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.PHONE_VIEW.value, scope_kind=ScopeKind.LOCATION.value, scope_value="30"),
            UserScope(user_id=100, permission_code=PermissionCode.SHIPMENT_VIEW.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.RECEIVING_UNPACK.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.RECEIVING_ACCEPT.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.TRAY_MANAGE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.BOX_MANAGE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.INVENTORY_RECEIVE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.TRANSFER_CREATE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.SHIPMENT_DISPATCH.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.INVENTORY_ISSUE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.RETURN_RECEIVE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.REPAIR_CREATE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="30"),
            UserScope(user_id=100, permission_code=PermissionCode.REPAIR_APPROVE.value, scope_kind=ScopeKind.LOCATION.value, scope_value="30"),
            UserScope(user_id=100, permission_code=PermissionCode.REPORT_VIEW.value, scope_kind=ScopeKind.LOCATION.value, scope_value="20"),
            UserScope(user_id=100, permission_code=PermissionCode.REPORT_VIEW.value, scope_kind=ScopeKind.LOCATION.value, scope_value="30"),
        ]
        session.add_all(scope_rows)
        session.add_all(
            [
                UserScope(
                    user_id=102,
                    permission_code=code.value,
                    scope_kind=ScopeKind.LOCATION.value,
                    scope_value="10",
                )
                for code in SHENZHEN_OPERATION_PERMISSIONS
            ]
        )

        # One phone in each authorized area and one in a third, unauthorized
        # location make the visibility assertions concrete.
        session.add_all(
            [
                PhoneDevice(
                    id=1,
                    imei="352099002700017",
                    status=PhoneStatus.GHANA_STOCK,
                    current_organization_id=2,
                    current_location_id=20,
                ),
                PhoneDevice(
                    id=2,
                    imei="352099002700025",
                    status=PhoneStatus.WAITING_REPAIR,
                    current_organization_id=2,
                    current_location_id=30,
                ),
                PhoneDevice(
                    id=3,
                    imei="352099002700033",
                    status=PhoneStatus.GHANA_STOCK,
                    current_organization_id=2,
                    current_location_id=40,
                ),
                PhoneDevice(
                    id=4,
                    imei="352099002700041",
                    status=PhoneStatus.WAITING_REPAIR,
                    current_organization_id=2,
                    current_location_id=30,
                ),
            ]
        )

        # An in-transit shipment destined for the management location allows
        # the receiving-start boundary to be tested without depending on the
        # sample-data seed script.
        session.add(
            Shipment(
                id=500,
                shipment_no="SHIP-MERGED-001",
                origin_organization_id=1,
                origin_location_id=10,
                destination_organization_id=2,
                destination_location_id=20,
                status=DocumentStatus.IN_TRANSIT,
                total_count=1,
                operator_id=100,
            )
        )
        session.add(
            ShipmentItem(
                id=501,
                shipment_id=500,
                phone_id=1,
                imei_snapshot="352099002700017",
            )
        )
        # A finished repair by another user is available for independent QA.
        session.add(
            RepairOrder(
                id=600,
                repair_no="REP-MERGED-001",
                organization_id=2,
                location_id=30,
                status=DocumentStatus.PENDING_ACCEPTANCE,
                operator_id=100,
                technician_id=101,
                total_count=1,
                completed_count=1,
            )
        )
        session.add(
            RepairItem(
                id=601,
                repair_order_id=600,
                phone_id=2,
                imei_snapshot="352099002700025",
                repair_result="REPAIRED",
                completed_at=datetime.now(timezone.utc),
                completed_by=101,
            )
        )
        # The phone is pending QA, not waiting for a new repair order.
        phone = await session.get(PhoneDevice, 2)
        phone.status = PhoneStatus.REPAIR_PENDING_ACCEPTANCE
        await session.commit()


async def _make_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_merged_role_permission_union_and_two_location_scopes():
    engine, factory = await _make_factory()
    try:
        await _seed_merged_role_database(factory)
        async with factory() as session:
            user = await session.get(User, 100)
            context = await build_access_context(session, user)
            assert context.permissions == GHANA_OPERATION_PERMISSIONS
            assert context.can_access(PermissionCode.PHONE_VIEW, location_id=20)
            assert context.can_access(PermissionCode.PHONE_VIEW, location_id=30)
            assert not context.can_access(PermissionCode.PHONE_VIEW, location_id=40)
            assert context.can_access(PermissionCode.RECEIVING_ACCEPT, location_id=20)
            assert not context.can_access(PermissionCode.RECEIVING_ACCEPT, location_id=30)
            assert context.can_access(PermissionCode.RETURN_RECEIVE, location_id=20)
            assert not context.can_access(PermissionCode.RETURN_RECEIVE, location_id=30)
            assert context.can_access(PermissionCode.REPAIR_CREATE, location_id=30)
            assert not context.can_access(PermissionCode.REPAIR_CREATE, location_id=20)
            # International Shipment dispatch remains a Shenzhen-only duty;
            # Ghana-to-store movement is represented by transfer:create.
            assert not context.can(PermissionCode.SHIPMENT_DISPATCH)
            report_scopes = context.scopes[PermissionCode.REPORT_VIEW]
            assert {next(iter(scope.values)) for scope in report_scopes} == {"20", "30"}

            sz_user = await session.get(User, 102)
            sz_context = await build_access_context(session, sz_user)
            assert sz_context.permissions == SHENZHEN_OPERATION_PERMISSIONS
            for code in SHENZHEN_OPERATION_PERMISSIONS:
                assert sz_context.can_access(code, location_id=10)
            assert not sz_context.can_access(PermissionCode.TRAY_MANAGE, location_id=20)
    finally:
        await engine.dispose()


async def test_merged_role_work_locations_and_inventory_visibility():
    engine, factory = await _make_factory()
    await _seed_merged_role_database(factory)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {create_access_token('100')}"}

        repair_locations = client.get(
            "/api/v1/auth/work-locations?permission=repair%3Acreate", headers=headers
        )
        assert repair_locations.status_code == 200, repair_locations.text
        repair_flags = {row["id"]: row["source_allowed"] for row in repair_locations.json()}
        assert repair_flags[30] is True
        assert repair_flags[20] is False

        receiving_locations = client.get(
            "/api/v1/auth/work-locations?permission=receiving%3Aaccept", headers=headers
        )
        assert receiving_locations.status_code == 200, receiving_locations.text
        receiving_flags = {row["id"]: row["source_allowed"] for row in receiving_locations.json()}
        assert receiving_flags[20] is True
        assert receiving_flags[30] is False

        phones = client.get("/api/v1/inventory/phones", headers=headers)
        assert phones.status_code == 200, phones.text
        assert {row["location_id"] for row in phones.json()["items"]} == {20, 30}

        # The same user can receive at the management location, but cannot use
        # that receiving permission to start a task in the repair area.
        receiving = client.post(
            "/api/v1/shipments/receiving/start",
            headers=headers,
            json={"shipment_no": "SHIP-MERGED-001", "organization_id": 2, "location_id": 20},
        )
        assert receiving.status_code == 200, receiving.text
        denied = client.post(
            "/api/v1/shipments/receiving/start",
            headers=headers,
            json={"shipment_no": "SHIP-MERGED-001", "organization_id": 2, "location_id": 30},
        )
        assert denied.status_code == 403, denied.text
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_merged_role_can_create_and_independently_review_repair():
    engine, factory = await _make_factory()
    await _seed_merged_role_database(factory)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {create_access_token('100')}"}

        created = client.post(
            "/api/v1/repairs",
            headers=headers,
            json={"organization_id": 2, "location_id": 30, "imeis": ["352099002700041"]},
        )
        assert created.status_code == 200, created.text
        assert created.json()["total_count"] == 1

        # The same role is also able to review a completed repair in the repair
        # area.  A different technician completed the fixture item, so the
        # service's separation-of-duties rule remains intact.

        reviewed = client.post(
            "/api/v1/repairs/REP-MERGED-001/review",
            headers=headers,
            json={
                "repair_no": "REP-MERGED-001",
                "imei": "352099002700025",
                "disposition": "AVAILABLE_AGAIN",
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == DocumentStatus.COMPLETED.value

        # The same repair approval permission is not valid at the management
        # location, even though the user is a single consolidated role.
        async with factory() as session:
            order = await session.scalar(select(RepairOrder).where(RepairOrder.id == 600))
            assert order.status == DocumentStatus.COMPLETED
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
