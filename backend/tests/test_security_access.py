import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.access import AccessContext, Scope, require_access
from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.base import Base
from app.db.models import User
from app.db.session import get_db
from app.main import app


def test_password_hash_and_jwt_round_trip():
    password_hash = hash_password("correct-password")
    assert password_hash != "correct-password"
    assert verify_password("correct-password", password_hash)
    assert not verify_password("wrong-password", password_hash)
    token = create_access_token("user-7")
    assert decode_access_token(token) == "user-7"


def test_access_requires_permission_and_scope():
    context = AccessContext(
        user_id=7,
        permissions={PermissionCode.PHONE_VIEW},
        scopes={PermissionCode.PHONE_VIEW: [Scope(ScopeKind.LOCATION, {"10"})]},
    )
    require_access(context, PermissionCode.PHONE_VIEW, location_id=10)
    with pytest.raises(PermissionError):
        require_access(context, PermissionCode.PHONE_VIEW, location_id=11)
    with pytest.raises(PermissionError):
        require_access(context, PermissionCode.SALES_CREATE, location_id=10)

    no_scope = AccessContext(user_id=7, permissions={PermissionCode.PHONE_VIEW})
    with pytest.raises(PermissionError):
        require_access(no_scope, PermissionCode.PHONE_VIEW, location_id=10)


def test_bearer_dependency_is_wired():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(User(id=7, phone="233000000000", display_name="测试用户", is_active=True))
            await session.commit()

        async def override_get_db():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            assert client.get("/api/v1/auth/me").status_code == 401
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {create_access_token('7')}"},
            )
            assert response.status_code == 200
            assert response.json() == {
                "id": 7,
                "username": None,
                "phone": "233000000000",
                "display_name": "测试用户",
                "permissions": [],
                "scopes": {},
            }
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    import asyncio
    asyncio.run(run())


def test_password_login_returns_access_token():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                User(
                    id=8,
                    phone="233000000001",
                    password_hash=hash_password("test-password"),
                    display_name="密码用户",
                    is_active=True,
                )
            )
            await session.commit()

        async def override_get_db():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            response = TestClient(app).post(
                "/api/v1/auth/password",
                json={"identifier": "233000000001", "password": "test-password"},
            )
            assert response.status_code == 200
            assert response.json()["token_type"] == "bearer"
            assert response.json()["user"]["id"] == 8
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    import asyncio
    asyncio.run(run())
