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
    RepairItem,
    ReturnItem,
    ReturnOrder,
    Role,
    RolePermission,
    User,
    UserRole,
    UserScope,
)
from app.db.session import get_db
from app.domain.enums import DocumentStatus, PhoneStatus
from app.main import app


async def test_returned_phone_repair_and_management_review():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="GH-HQ", name="加纳管理处", country="GH"),
                Location(id=10, organization_id=1, code="REPAIR", name="维修区", location_type="repair"),
                User(id=100, phone="233000000100", display_name="管理处建单员"),
                User(id=101, phone="233000000101", display_name="维修人员"),
                User(id=102, phone="233000000102", display_name="管理处验收员"),
                Role(id=200, code="repair_creator", name="维修建单"),
                Role(id=201, code="technician", name="维修人员"),
                Role(id=202, code="repair_reviewer", name="维修验收"),
                PhoneDevice(id=300, imei="355240577857876", status=PhoneStatus.WAITING_REPAIR, current_organization_id=1, current_location_id=10),
                ReturnOrder(
                    id=400, return_no="RET-001", sales_order_id=999,
                    source_organization_id=1, source_location_id=10,
                    destination_organization_id=1, destination_location_id=10,
                    status=DocumentStatus.COMPLETED, total_count=1, received_count=1,
                ),
                ReturnItem(return_order_id=400, phone_id=300, imei_snapshot="355240577857876"),
            ]
        )
        permission_defs = [
            (500, PermissionCode.REPAIR_CREATE, 200, 100),
            (501, PermissionCode.REPAIR_RECEIVE, 201, 101),
            (502, PermissionCode.REPAIR_UPDATE, 201, 101),
            (503, PermissionCode.REPAIR_APPROVE, 202, 102),
        ]
        for permission_id, code, role_id, user_id in permission_defs:
            session.add(Permission(id=permission_id, code=code, name=code))
            session.add(RolePermission(role_id=role_id, permission_id=permission_id))
            session.add(UserScope(user_id=user_id, permission_code=code, scope_kind=ScopeKind.LOCATION, scope_value="10"))
        session.add_all(
            [
                UserRole(user_id=100, role_id=200),
                UserRole(user_id=101, role_id=201),
                UserRole(user_id=102, role_id=202),
            ]
        )
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        create_headers = {
            "Authorization": f"Bearer {create_access_token('100')}",
            "X-Idempotency-Key": "repair-create-replay-001",
        }
        created = client.post(
            "/api/v1/repairs",
            headers=create_headers,
            json={"organization_id": 1, "location_id": 10, "return_no": "RET-001", "imeis": ["355240577857876"]},
        )
        assert created.status_code == 200, created.text
        repair_no = created.json()["repair_no"]
        assert created.json()["status"] == "待审核"

        replayed = client.post(
            "/api/v1/repairs",
            headers=create_headers,
            json={"organization_id": 1, "location_id": 10, "return_no": "RET-001", "imeis": ["355240577857876"]},
        )
        assert replayed.status_code == 200, replayed.text
        assert replayed.json() == created.json()

        accepted = client.post(
            f"/api/v1/repairs/{repair_no}/accept",
            headers={"Authorization": f"Bearer {create_access_token('101')}"},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "处理中"

        completed = client.post(
            f"/api/v1/repairs/{repair_no}/complete",
            headers={"Authorization": f"Bearer {create_access_token('101')}"},
            json={
                "repair_no": repair_no, "imei": "355240577857876",
                "diagnosis": "屏幕排线松动", "work_done": "重新安装排线",
                "parts": [], "repair_cost": "20.00", "repair_result": "REPAIRED",
            },
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "待验收"

        self_review = client.post(
            f"/api/v1/repairs/{repair_no}/review",
            headers={"Authorization": f"Bearer {create_access_token('101')}"},
            json={"repair_no": repair_no, "imei": "355240577857876", "disposition": "AVAILABLE_AGAIN"},
        )
        assert self_review.status_code == 403

        reviewed = client.post(
            f"/api/v1/repairs/{repair_no}/review",
            headers={"Authorization": f"Bearer {create_access_token('102')}"},
            json={"repair_no": repair_no, "imei": "355240577857876", "disposition": "AVAILABLE_AGAIN"},
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "已完成"

        async with factory() as session:
            phone = await session.get(PhoneDevice, 300)
            item = await session.scalar(select(RepairItem).where(RepairItem.phone_id == 300))
            assert phone.status == PhoneStatus.AVAILABLE_AGAIN
            assert item.diagnosis == "屏幕排线松动"
            assert item.completed_by == 101
            assert item.accepted_by == 102
            actions = list(await session.scalars(select(InventoryTransaction.action).order_by(InventoryTransaction.id)))
            assert actions == ["创建送修单", "维修人员接收", "维修完成待验收", "维修结果验收"]
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
