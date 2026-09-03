"""Create or update a username-based super administrator.

The database URL and password are intentionally supplied at runtime. This
script never prints the password or stores it in source control.
"""
import argparse
import asyncio
import getpass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import hash_password
from app.db.models import Permission, Role, RolePermission, User, UserRole, UserScope


async def bootstrap(database_url: str, username: str, password: str, display_name: str) -> int:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = await session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(username=username, phone=None, display_name=display_name, is_active=True)
                session.add(user)
                await session.flush()
            else:
                user.display_name = display_name
                user.is_active = True
            user.password_hash = hash_password(password)

            role = await session.scalar(select(Role).where(Role.code == "super_admin"))
            if role is None:
                role = Role(code="super_admin", name="超级管理员")
                session.add(role)
                await session.flush()

            permission_rows: dict[str, Permission] = {}
            for code in PermissionCode:
                permission = await session.scalar(select(Permission).where(Permission.code == code.value))
                if permission is None:
                    permission = Permission(code=code.value, name=code.value)
                    session.add(permission)
                    await session.flush()
                permission_rows[code.value] = permission

                link = await session.scalar(select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                ))
                if link is None:
                    session.add(RolePermission(role_id=role.id, permission_id=permission.id))

                scope = await session.scalar(select(UserScope).where(
                    UserScope.user_id == user.id,
                    UserScope.permission_code == code.value,
                    UserScope.scope_kind == ScopeKind.ALL.value,
                    UserScope.scope_value.is_(None),
                ))
                if scope is None:
                    session.add(UserScope(
                        user_id=user.id, permission_code=code.value,
                        scope_kind=ScopeKind.ALL.value, scope_value=None,
                    ))

            user_role = await session.scalar(select(UserRole).where(
                UserRole.user_id == user.id, UserRole.role_id == role.id,
            ))
            if user_role is None:
                session.add(UserRole(user_id=user.id, role_id=role.id))
            await session.commit()
            return user.id
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化或更新超级管理员")
    parser.add_argument("--database-url", required=True, help="应用数据库 SQLAlchemy 异步连接串")
    parser.add_argument("--username", default="xiaojiang")
    parser.add_argument("--display-name", default="超级管理员")
    args = parser.parse_args()
    password = getpass.getpass("超级管理员密码（不会显示）: ")
    if len(password) < 8:
        raise SystemExit("密码至少需要 8 个字符")
    user_id = asyncio.run(bootstrap(args.database_url, args.username, password, args.display_name))
    print(f"超级管理员已初始化，用户 ID: {user_id}。密码未输出。")


if __name__ == "__main__":
    main()
