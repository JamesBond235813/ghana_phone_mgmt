from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.permissions import PermissionCode, ScopeKind
from app.db.base import Base
from app.db.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    UserScope,
)
from app.repositories.users import build_access_context


async def test_database_permissions_and_scopes_build_access_context():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(id=11, phone="233000000011", display_name="门店店员")
        role = Role(id=21, code="store_clerk", name="门店店员")
        permission = Permission(id=31, code=PermissionCode.SALES_CREATE, name="创建销售")
        session.add_all(
            [
                user,
                role,
                permission,
                UserRole(user_id=11, role_id=21),
                RolePermission(role_id=21, permission_id=31),
                UserScope(
                    user_id=11,
                    permission_code=PermissionCode.SALES_CREATE,
                    scope_kind=ScopeKind.LOCATION,
                    scope_value="1001",
                ),
            ]
        )
        await session.commit()
        context = await build_access_context(session, user)
        assert context.can_access(PermissionCode.SALES_CREATE, location_id=1001)
        assert not context.can_access(PermissionCode.SALES_CREATE, location_id=1002)
        assert not context.can(PermissionCode.SALES_APPROVE)
    await engine.dispose()
