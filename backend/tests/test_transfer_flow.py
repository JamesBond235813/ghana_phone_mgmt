from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models import (
    Box,
    Location,
    Organization,
    Permission,
    PhoneDevice,
    PhoneTrayRelation,
    Role,
    RolePermission,
    TransferItem,
    Tray,
    TrayBoxRelation,
    User,
    UserRole,
    UserScope,
)
from app.db.session import get_db
from app.domain.enums import PhoneStatus
from app.main import app


async def test_management_office_to_store_partial_receipt():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        now = datetime.now(timezone.utc)
        session.add_all(
            [
                Organization(id=1, code="GH-HQ", name="加纳管理处", country="GH"),
                Organization(id=2, code="STORE-A", name="门店A", country="GH"),
                Location(id=10, organization_id=1, code="GH-WH", name="管理处仓库", location_type="warehouse"),
                Location(id=20, organization_id=2, code="STORE-A-WH", name="门店A库存", location_type="store"),
                User(id=100, phone="233000000100", display_name="管理处仓库员"),
                User(id=101, phone="233000000101", display_name="门店收货员"),
                Role(id=200, code="issuer", name="出库员"),
                Role(id=201, code="receiver", name="收货员"),
                Box(id=300, code="BOX-GH-001", current_location_id=10),
                Tray(id=301, code="TP-GH-001", current_location_id=10, current_box_id=300),
                PhoneDevice(id=400, imei="355240577857876", status=PhoneStatus.GHANA_STOCK, current_organization_id=1, current_location_id=10, current_tray_id=301),
                PhoneDevice(id=401, imei="355240577857884", status=PhoneStatus.GHANA_STOCK, current_organization_id=1, current_location_id=10, current_tray_id=301),
                PhoneTrayRelation(phone_id=400, tray_id=301, started_at=now),
                PhoneTrayRelation(phone_id=401, tray_id=301, started_at=now),
                TrayBoxRelation(tray_id=301, box_id=300, started_at=now),
            ]
        )
        permissions = [
            Permission(id=500, code=PermissionCode.TRANSFER_CREATE, name="调拨出库"),
            Permission(id=501, code=PermissionCode.TRANSFER_RECEIVE, name="调拨收货"),
        ]
        session.add_all(permissions)
        session.add_all(
            [
                UserRole(user_id=100, role_id=200),
                UserRole(user_id=101, role_id=201),
                RolePermission(role_id=200, permission_id=500),
                RolePermission(role_id=201, permission_id=501),
                UserScope(user_id=100, permission_code=PermissionCode.TRANSFER_CREATE, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=101, permission_code=PermissionCode.TRANSFER_RECEIVE, scope_kind=ScopeKind.LOCATION, scope_value="20"),
            ]
        )
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        issue = client.post(
            "/api/v1/transfers/issue",
            headers={"Authorization": f"Bearer {create_access_token('100')}"},
            json={
                "source_organization_id": 1,
                "source_location_id": 10,
                "destination_organization_id": 2,
                "destination_location_id": 20,
                "containers": [{"kind": "BOX", "code": "BOX-GH-001"}],
            },
        )
        assert issue.status_code == 200, issue.text
        transfer_no = issue.json()["transfer_no"]
        assert issue.json()["total_count"] == 2

        receive = client.post(
            "/api/v1/transfers/receive",
            headers={"Authorization": f"Bearer {create_access_token('101')}"},
            json={
                "transfer_no": transfer_no,
                "received_imeis": ["355240577857876"],
                "complete": True,
            },
        )
        assert receive.status_code == 200, receive.text
        assert receive.json()["status"] == "部分差异"
        assert receive.json()["received_count"] == 1
        assert receive.json()["exception_count"] == 1

        async with factory() as session:
            received = await session.get(PhoneDevice, 400)
            missing = await session.get(PhoneDevice, 401)
            tray = await session.get(Tray, 301)
            box = await session.get(Box, 300)
            assert received.status == PhoneStatus.STORE_STOCK
            assert received.current_location_id == 20
            assert received.current_tray_id == 301
            assert missing.status == PhoneStatus.FROZEN
            assert missing.current_location_id is None
            assert missing.current_tray_id is None
            assert tray.current_location_id == 20
            assert box.current_location_id == 20
            missing_item = await session.scalar(
                select(TransferItem).where(TransferItem.imei_snapshot == "355240577857884")
            )
            assert missing_item.received_at is None
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
