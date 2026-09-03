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
    PhoneDevice,
    Role,
    RolePermission,
    Shipment,
    SalesOrder,
    User,
    UserRole,
    UserScope,
)
from app.db.session import get_db
from app.domain.enums import DocumentStatus, PhoneStatus
from app.main import app


async def _setup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    permission_codes = [
        PermissionCode.USER_MANAGE,
        PermissionCode.ROLE_MANAGE,
        PermissionCode.PHONE_VIEW,
        PermissionCode.REPORT_VIEW,
        PermissionCode.AUDIT_VIEW,
    ]
    async with factory() as session:
        session.add_all([
            Organization(id=1, code="GH", name="加纳", country="GH"),
            Organization(id=2, code="STORE-A", name="门店A", country="GH"),
            Location(id=10, organization_id=1, code="HQ", name="管理处", location_type="warehouse"),
            Location(id=20, organization_id=2, code="A", name="门店A", location_type="store"),
            Location(id=21, organization_id=2, code="B", name="门店B", location_type="store"),
            User(id=100, phone="233000000100", display_name="管理员"),
            User(id=101, phone="233000000101", display_name="门店用户"),
            Role(id=200, code="admin", name="管理员"),
            Role(id=201, code="store", name="门店用户"),
            PhoneDevice(id=300, imei="355240577857876", status=PhoneStatus.STORE_STOCK, current_organization_id=2, current_location_id=20),
            PhoneDevice(id=301, imei="355240577857884", status=PhoneStatus.STORE_STOCK, current_organization_id=2, current_location_id=21),
            SalesOrder(id=700, sales_no="SALE-TEST-001", organization_id=2, location_id=20, sales_type="RETAIL", status=DocumentStatus.COMPLETED, total_count=1, total_amount="123.45"),
        ])
        permissions = [Permission(id=400 + index, code=code, name=str(code)) for index, code in enumerate(permission_codes)]
        session.add_all(permissions)
        session.add_all([
            UserRole(user_id=100, role_id=200),
            UserRole(user_id=101, role_id=201),
            RolePermission(role_id=200, permission_id=400),
            RolePermission(role_id=200, permission_id=401),
            RolePermission(role_id=200, permission_id=402),
            RolePermission(role_id=200, permission_id=403),
            RolePermission(role_id=200, permission_id=404),
            RolePermission(role_id=201, permission_id=402),
            UserScope(user_id=100, permission_code=PermissionCode.USER_MANAGE, scope_kind=ScopeKind.ALL),
            UserScope(user_id=100, permission_code=PermissionCode.ROLE_MANAGE, scope_kind=ScopeKind.ALL),
            UserScope(user_id=100, permission_code=PermissionCode.PHONE_VIEW, scope_kind=ScopeKind.ALL),
            UserScope(user_id=100, permission_code=PermissionCode.REPORT_VIEW, scope_kind=ScopeKind.ALL),
            UserScope(user_id=100, permission_code=PermissionCode.AUDIT_VIEW, scope_kind=ScopeKind.ALL),
            UserScope(user_id=101, permission_code=PermissionCode.PHONE_VIEW, scope_kind=ScopeKind.LOCATION, scope_value="20"),
        ])
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return engine, factory


async def test_admin_requires_global_scope_and_queries_are_isolated():
    engine, factory = await _setup()
    try:
        client = TestClient(app)
        no_auth = client.get("/api/v1/admin/users")
        assert no_auth.status_code == 401

        store_headers = {"Authorization": f"Bearer {create_access_token('101')}"}
        assert client.get("/api/v1/admin/users", headers=store_headers).status_code == 403
        inventory = client.get("/api/v1/inventory/phones", headers=store_headers)
        assert inventory.status_code == 200
        assert [item["imei"] for item in inventory.json()["items"]] == ["355240577857876"]
        work_locations = client.get("/api/v1/auth/work-locations", headers=store_headers)
        assert work_locations.status_code == 200
        assert {item["id"] for item in work_locations.json() if item["source_allowed"]} == {20}
        assert client.get("/api/v1/admin/audits", headers=store_headers).status_code == 403
        store_documents = client.get("/api/v1/documents", headers=store_headers)
        assert store_documents.status_code == 200
        sale_rows = [item for item in store_documents.json()["items"] if item["type"] == "sales"]
        assert sale_rows and "total_amount" not in sale_rows[0]

        admin_headers = {"Authorization": f"Bearer {create_access_token('100')}"}
        admin_locations = client.get("/api/v1/auth/work-locations", headers=admin_headers)
        assert admin_locations.status_code == 200
        assert {item["id"] for item in admin_locations.json()} == {10, 20, 21}
        organizations = client.get("/api/v1/admin/organizations", headers=admin_headers)
        assert organizations.status_code == 200
        created = client.post(
            "/api/v1/admin/organizations",
            headers=admin_headers,
            json={"code": "SZ", "name": "深圳网点", "country": "CN"},
        )
        assert created.status_code == 200
        organization_id = created.json()["id"]
        location = client.post(
            "/api/v1/admin/locations",
            headers=admin_headers,
            json={"organization_id": organization_id, "code": "SZ-WH", "name": "深圳仓库", "location_type": "warehouse"},
        )
        assert location.status_code == 200
        location_update = client.patch(
            f"/api/v1/admin/locations/{location.json()['id']}",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert location_update.status_code == 200
        organization_update = client.patch(
            f"/api/v1/admin/organizations/{organization_id}",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert organization_update.status_code == 200
        role = client.post(
            "/api/v1/admin/roles",
            headers=admin_headers,
            json={"code": "viewer", "name": "查看员", "permission_codes": ["phone:view"]},
        )
        assert role.status_code == 200
        role_update = client.patch(
            f"/api/v1/admin/roles/{role.json()['id']}",
            headers=admin_headers,
            json={"name": "查看员（更新）", "permission_codes": ["phone:view"]},
        )
        assert role_update.status_code == 200
        user = client.post(
            "/api/v1/admin/users",
            headers=admin_headers,
            json={"phone": "233000000102", "display_name": "新用户", "password": "password-123", "role_ids": [role.json()["id"]]},
        )
        assert user.status_code == 200
        updated = client.patch(
            f"/api/v1/admin/users/{user.json()['id']}",
            headers=admin_headers,
            json={"display_name": "已停用用户", "is_active": False},
        )
        assert updated.status_code == 200
        assert updated.json()["is_active"] is False
        self_disable = client.patch(
            "/api/v1/admin/users/100",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert self_disable.status_code == 400
        audits = client.get("/api/v1/admin/audits?resource_type=organization", headers=admin_headers)
        assert audits.status_code == 200
        assert any(item["action"] == "创建组织" and item["resource_id"] == str(organization_id) for item in audits.json())
        admin_documents = client.get("/api/v1/documents", headers=admin_headers)
        admin_sale = next(item for item in admin_documents.json()["items"] if item["type"] == "sales")
        assert admin_sale["total_amount"] == "123.45"
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_admin_cannot_grant_unowned_permission_or_scope():
    engine, factory = await _setup()
    try:
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {create_access_token('100')}"}
        response = client.post(
            "/api/v1/admin/users",
            headers=headers,
            json={
                "phone": "233000000103",
                "display_name": "越权用户",
                "password": "password-123",
                "scopes": [{"permission_code": "sales:create", "scope_kind": "all"}],
            },
        )
        assert response.status_code == 403
        async with factory() as session:
            assert await session.scalar(select(User).where(User.phone == "233000000103")) is None
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
