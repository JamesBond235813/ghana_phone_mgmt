from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models import (
    Box,
    InventoryTransaction,
    Location,
    Organization,
    Permission,
    Role,
    RolePermission,
    Tray,
    TrayBoxRelation,
    ShipmentItem,
    User,
    UserRole,
    UserScope,
    PhoneDevice,
)
from app.db.session import get_db
from app.domain.enums import PhoneStatus
from app.main import app


async def test_dispatch_receive_unpack_and_inspect():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="SZ", name="深圳", country="CN"),
                Organization(id=2, code="GH", name="加纳", country="GH"),
                Location(id=10, organization_id=1, code="SZ-WH", name="深圳仓", location_type="warehouse"),
                Location(id=20, organization_id=2, code="GH-WH", name="加纳管理处", location_type="warehouse"),
                User(id=100, phone="8613800000000", display_name="深圳发运员"),
                User(id=101, phone="233000000001", display_name="加纳接收员"),
                Role(id=200, code="shipment_operator", name="发运操作员"),
                Role(id=201, code="receiving_operator", name="接收操作员"),
                Tray(id=300, code="TP-SZ-001", current_location_id=10, current_box_id=400),
                Box(id=400, code="BOX-SZ-001", current_location_id=10),
                PhoneDevice(id=500, imei="355240577857876", status=PhoneStatus.SHENZHEN_STOCK, current_organization_id=1, current_location_id=10, current_tray_id=300),
                PhoneDevice(id=501, imei="355240577857884", status=PhoneStatus.SHENZHEN_STOCK, current_organization_id=1, current_location_id=10, current_tray_id=300),
                TrayBoxRelation(tray_id=300, box_id=400, started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
            ]
        )
        permissions = [
            Permission(id=600 + i, code=code, name=code)
            for i, code in enumerate(
                [
                    PermissionCode.SHIPMENT_DISPATCH,
                    PermissionCode.RECEIVING_UNPACK,
                    PermissionCode.RECEIVING_ACCEPT,
                    PermissionCode.PHONE_VIEW,
                ]
            )
        ]
        session.add_all(permissions)
        session.add_all(
            [
                UserRole(user_id=100, role_id=200), UserRole(user_id=101, role_id=201),
                UserScope(user_id=100, permission_code=PermissionCode.SHIPMENT_DISPATCH, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=100, permission_code=PermissionCode.PHONE_VIEW, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=101, permission_code=PermissionCode.RECEIVING_UNPACK, scope_kind=ScopeKind.LOCATION, scope_value="20"),
                UserScope(user_id=101, permission_code=PermissionCode.RECEIVING_ACCEPT, scope_kind=ScopeKind.LOCATION, scope_value="20"),
                UserScope(user_id=101, permission_code=PermissionCode.PHONE_VIEW, scope_kind=ScopeKind.LOCATION, scope_value="20"),
            ]
        )
        for permission in permissions:
            session.add(RolePermission(role_id=200, permission_id=permission.id))
            session.add(RolePermission(role_id=201, permission_id=permission.id))
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        dispatch = client.post(
            "/api/v1/shipments/dispatch",
            headers={"Authorization": f"Bearer {create_access_token('100')}"},
            json={
                "origin_organization_id": 1, "origin_location_id": 10,
                "destination_organization_id": 2, "destination_location_id": 20,
                "containers": [{"kind": "BOX", "code": "BOX-SZ-001"}],
            },
        )
        assert dispatch.status_code == 200, dispatch.text
        shipment_no = dispatch.json()["shipment_no"]
        assert dispatch.json()["total_count"] == 2

        receiving = client.post(
            "/api/v1/shipments/receiving/start",
            headers={"Authorization": f"Bearer {create_access_token('101')}"},
            json={"shipment_no": shipment_no, "organization_id": 2, "location_id": 20},
        )
        assert receiving.status_code == 200, receiving.text
        receiving_no = receiving.json()["receiving_no"]

        accepted = client.post(
            "/api/v1/shipments/receiving/inspect",
            headers={"Authorization": f"Bearer {create_access_token('101')}"},
            json={
                "receiving_no": receiving_no,
                "imei": "355240577857876",
                "accepted": True,
                "target_tray_code": "TP-GH-NEW",
                "target_box_code": "BOX-GH-NEW",
            },
        )
        assert accepted.status_code == 200, accepted.text
        exception = client.post(
            "/api/v1/shipments/receiving/inspect",
            headers={"Authorization": f"Bearer {create_access_token('101')}"},
            json={"receiving_no": receiving_no, "imei": "355240577857884", "accepted": False, "note": "运输损坏"},
        )
        assert exception.status_code == 200, exception.text
        assert exception.json()["status"] == "部分差异"

        async with factory() as session:
            phones = list(await session.scalars(select(PhoneDevice).order_by(PhoneDevice.id)))
            assert phones[0].status == PhoneStatus.GHANA_STOCK
            assert phones[1].status == PhoneStatus.FROZEN
            assert phones[0].current_organization_id == 2
            relation = await session.scalar(select(TrayBoxRelation).where(TrayBoxRelation.tray_id == 300))
            assert relation.ended_at is not None
            new_tray = await session.scalar(select(Tray).where(Tray.code == "TP-GH-NEW"))
            new_box = await session.scalar(select(Box).where(Box.code == "BOX-GH-NEW"))
            assert new_tray is not None and new_tray.current_location_id == 20
            assert new_box is not None and new_box.current_location_id == 20
            assert phones[0].current_tray_id == new_tray.id
            new_relation = await session.scalar(select(TrayBoxRelation).where(TrayBoxRelation.tray_id == new_tray.id))
            assert new_relation is not None and new_relation.box_id == new_box.id and new_relation.ended_at is None
            shipment_item = await session.scalar(select(ShipmentItem).where(ShipmentItem.imei_snapshot == "355240577857876"))
            assert shipment_item.source_tray_id == 300
            assert shipment_item.source_box_id == 400
            transactions = list(await session.scalars(select(InventoryTransaction).order_by(InventoryTransaction.id)))
            assert any(transaction.action == "深圳发运" for transaction in transactions)
            assert any(transaction.action == "加纳验收异常" for transaction in transactions)
            assert sum(transaction.action == "加纳到货待验收" for transaction in transactions) == 2
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
