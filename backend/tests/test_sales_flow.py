from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import create_access_token
from app.db.base import Base
from app.db.models import (
    InventoryTransaction,
    Location,
    Organization,
    Permission,
    PhoneDevice,
    Role,
    RolePermission,
    User,
    UserRole,
    UserScope,
)
from app.db.session import get_db
from app.domain.enums import PhoneStatus
from app.main import app


async def test_sale_confirm_and_return_to_management_office():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="STORE-A", name="门店A", country="GH"),
                Organization(id=2, code="GH-HQ", name="加纳管理处", country="GH"),
                Location(id=10, organization_id=1, code="STORE-A-WH", name="门店A库存", location_type="store"),
                Location(id=20, organization_id=2, code="GH-WH", name="管理处维修接收区", location_type="repair"),
                User(id=100, phone="233000000100", display_name="店员"),
                User(id=101, phone="233000000101", display_name="主管"),
                User(id=102, phone="233000000102", display_name="管理处接收员"),
                Role(id=200, code="clerk", name="店员"),
                Role(id=201, code="supervisor", name="主管"),
                Role(id=202, code="hq_receiver", name="管理处接收员"),
                PhoneDevice(id=300, imei="355240577857876", status=PhoneStatus.STORE_STOCK, current_organization_id=1, current_location_id=10),
            ]
        )
        permission_codes = [
            PermissionCode.SALES_CREATE, PermissionCode.SALES_APPROVE,
            PermissionCode.RETURN_CREATE, PermissionCode.RETURN_RECEIVE,
        ]
        permissions = [Permission(id=400 + i, code=code, name=code) for i, code in enumerate(permission_codes)]
        session.add_all(permissions)
        session.add_all(
            [
                UserRole(user_id=100, role_id=200), UserRole(user_id=101, role_id=201), UserRole(user_id=102, role_id=202),
                RolePermission(role_id=200, permission_id=400), RolePermission(role_id=200, permission_id=402),
                RolePermission(role_id=201, permission_id=401),
                RolePermission(role_id=202, permission_id=403),
                UserScope(user_id=100, permission_code=PermissionCode.SALES_CREATE, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=100, permission_code=PermissionCode.RETURN_CREATE, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=101, permission_code=PermissionCode.SALES_APPROVE, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=102, permission_code=PermissionCode.RETURN_RECEIVE, scope_kind=ScopeKind.LOCATION, scope_value="20"),
            ]
        )
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    clerk_headers = {"Authorization": f"Bearer {create_access_token('100')}"}
    supervisor_headers = {"Authorization": f"Bearer {create_access_token('101')}"}
    receiver_headers = {"Authorization": f"Bearer {create_access_token('102')}"}
    try:
        client = TestClient(app)
        sale = client.post(
            "/api/v1/sales",
            headers=clerk_headers,
            json={
                "organization_id": 1, "location_id": 10, "sales_type": "RETAIL",
                "containers": [{"kind": "PHONE", "code": "355240577857876"}],
                "prices": {"355240577857876": "120.00"},
            },
        )
        assert sale.status_code == 200, sale.text
        sales_no = sale.json()["sales_no"]

        duplicate = client.post(
            "/api/v1/sales",
            headers=clerk_headers,
            json={"organization_id": 1, "location_id": 10, "sales_type": "RETAIL", "containers": [{"kind": "PHONE", "code": "355240577857876"}]},
        )
        assert duplicate.status_code == 400

        confirmed = client.post(f"/api/v1/sales/{sales_no}/confirm", headers=supervisor_headers)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "已完成"

        returned = client.post(
            "/api/v1/returns",
            headers=clerk_headers,
            json={
                "sales_no": sales_no, "source_organization_id": 1, "source_location_id": 10,
                "destination_organization_id": 2, "destination_location_id": 20,
                "imeis": ["355240577857876"],
            },
        )
        assert returned.status_code == 200, returned.text
        return_no = returned.json()["return_no"]

        received = client.post(
            "/api/v1/returns/receive",
            headers=receiver_headers,
            json={"return_no": return_no, "received_imeis": ["355240577857876"]},
        )
        assert received.status_code == 200, received.text
        assert received.json()["status"] == "已完成"

        async with factory() as session:
            phone = await session.get(PhoneDevice, 300)
            assert phone.status == PhoneStatus.WAITING_REPAIR
            assert phone.current_organization_id == 2
            assert phone.current_location_id == 20
            actions = list(await session.scalars(select(InventoryTransaction.action).order_by(InventoryTransaction.id)))
            assert "销售确认" in actions
            assert "销售退回发出" in actions
            assert "管理处接收销售退回" in actions
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
