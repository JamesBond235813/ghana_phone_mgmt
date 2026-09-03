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
    Role,
    RolePermission,
    User,
    UserRole,
    UserScope,
)
from app.db.session import get_db
from app.main import app


async def seed_database(factory) -> None:
    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="SZ", name="深圳网点", country="CN"),
                Location(id=10, organization_id=1, code="SZ-WH", name="深圳仓", location_type="warehouse"),
                User(id=100, phone="8613800000000", display_name="深圳仓库员"),
                Role(id=200, code="sz_operator", name="深圳操作员"),
            ]
        )
        permissions = [
            Permission(id=300 + i, code=code, name=str(code))
            for i, code in enumerate(
                [
                    PermissionCode.PURCHASE_CREATE,
                    PermissionCode.TRAY_MANAGE,
                    PermissionCode.BOX_MANAGE,
                    PermissionCode.PHONE_VIEW,
                ]
            )
        ]
        session.add_all(permissions)
        session.add(UserRole(user_id=100, role_id=200))
        for permission in permissions:
            session.add(RolePermission(role_id=200, permission_id=permission.id))
        session.add_all(
            [
                UserScope(user_id=100, permission_code=PermissionCode.PURCHASE_CREATE, scope_kind=ScopeKind.ORGANIZATION, scope_value="1"),
                UserScope(user_id=100, permission_code=PermissionCode.TRAY_MANAGE, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=100, permission_code=PermissionCode.BOX_MANAGE, scope_kind=ScopeKind.LOCATION, scope_value="10"),
                UserScope(user_id=100, permission_code=PermissionCode.PHONE_VIEW, scope_kind=ScopeKind.LOCATION, scope_value="10"),
            ]
        )
        await session.commit()


async def test_purchase_to_box_and_phone_lookup_flow():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await seed_database(factory)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    headers = {"Authorization": f"Bearer {create_access_token('100')}"}
    try:
        client = TestClient(app)
        purchase = client.post(
            "/api/v1/inventory/purchase-receipts",
            headers={**headers, "X-Idempotency-Key": "purchase-test-key-1"},
            json={
                "organization_id": 1,
                "location_id": 10,
                "supplier": "测试供应商",
                "items": [
                    {"imei": "355240577857876", "brand": "Apple", "model": "iPhone 13", "storage": "128GB"}
                ],
            },
        )
        assert purchase.status_code == 200, purchase.text
        assert purchase.json()["total_count"] == 1

        repeated = client.post(
            "/api/v1/inventory/purchase-receipts",
            headers={**headers, "X-Idempotency-Key": "purchase-test-key-1"},
            json={
                "organization_id": 1, "location_id": 10,
                "supplier": "测试供应商",
                "items": [{"imei": "355240577857876", "brand": "Apple", "model": "iPhone 13", "storage": "128GB"}],
            },
        )
        assert repeated.status_code == 200, repeated.text
        repeated_again = client.post(
            "/api/v1/inventory/purchase-receipts",
            headers={**headers, "X-Idempotency-Key": "purchase-test-key-1"},
            json={
                "organization_id": 1, "location_id": 10,
                "supplier": "测试供应商",
                "items": [{"imei": "355240577857876", "brand": "Apple", "model": "iPhone 13", "storage": "128GB"}],
            },
        )
        assert repeated_again.status_code == 200
        assert repeated_again.json() == repeated.json()

        duplicate = client.post(
            "/api/v1/inventory/purchase-receipts",
            headers=headers,
            json={"organization_id": 1, "location_id": 10, "items": [{"imei": "355240577857876"}]},
        )
        assert duplicate.status_code == 400

        tray = client.post(
            "/api/v1/inventory/trays",
            headers=headers,
            json={"code": "TP-SZ-001", "location_id": 10, "imeis": ["355240577857876"]},
        )
        assert tray.status_code == 200, tray.text
        assert tray.json()["phone_count"] == 1

        box = client.post(
            "/api/v1/inventory/boxes",
            headers=headers,
            json={"code": "BOX-SZ-001", "location_id": 10, "tray_codes": ["TP-SZ-001"]},
        )
        assert box.status_code == 200, box.text
        assert box.json()["phone_count"] == 1

        phone = client.get("/api/v1/inventory/phones/355240577857876", headers=headers)
        assert phone.status_code == 200
        assert phone.json()["tray_code"] == "TP-SZ-001"
        assert phone.json()["box_code"] == "BOX-SZ-001"

        async with factory() as session:
            actions = list(await session.scalars(select(InventoryTransaction.action).order_by(InventoryTransaction.id)))
            assert actions == ["采购入库", "装入托盘", "装入箱子"]
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
