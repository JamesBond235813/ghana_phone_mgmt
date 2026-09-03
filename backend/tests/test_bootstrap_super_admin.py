from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import verify_password
from app.db.base import Base
from app.db.models import RolePermission, User, UserRole, UserScope
from scripts.bootstrap_super_admin import bootstrap


async def test_bootstrap_super_admin_is_idempotent_and_global():
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db") as database:
        database.close()
        database_url = f"sqlite+aiosqlite:///{database.name}"
        setup_engine = create_async_engine(database_url)
        async with setup_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await setup_engine.dispose()

        user_id = await bootstrap(database_url, "root-test", "test-password-123", "测试超级管理员")
        same_user_id = await bootstrap(database_url, "root-test", "test-password-123", "测试超级管理员")
        assert same_user_id == user_id

        check_engine = create_async_engine(database_url)
        check_factory = async_sessionmaker(check_engine, expire_on_commit=False)
        async with check_factory() as session:
            user = await session.get(User, user_id)
            assert user is not None and user.username == "root-test" and user.phone is None
            assert verify_password("test-password-123", user.password_hash)
            role_id = await session.scalar(select(UserRole.role_id).where(UserRole.user_id == user_id))
            assert role_id is not None
            permission_count = await session.scalar(select(func.count(RolePermission.permission_id)).where(RolePermission.role_id == role_id))
            assert permission_count == len(list(PermissionCode))
            scopes = list(await session.scalars(select(UserScope).where(UserScope.user_id == user_id)))
            assert len(scopes) == len(list(PermissionCode))
            assert all(scope.scope_kind == ScopeKind.ALL.value for scope in scopes)
        await check_engine.dispose()
