from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import AccessContext, Scope
from app.core.permissions import PermissionCode, ScopeKind
from app.core.security import verify_password
from app.core.roles import get_role_metadata
from app.db.models import Permission, Role, RolePermission, User, UserRole, UserScope


DUMMY_PASSWORD_HASH = (
    "scrypt$16384$8$1$MDEyMzQ1Njc4OWFiY2RlZg==$"
    "WZ5xV1IUa3QZG-mppEAARQPnM2qz9pYSfG0gRFcUjEo="
)


async def get_active_user_by_phone(session: AsyncSession, phone: str) -> User | None:
    return await session.scalar(
        select(User).where(User.phone == phone, User.is_active.is_(True))
    )


async def authenticate_password(
    session: AsyncSession, identifier: str, password: str
) -> User | None:
    user = await session.scalar(select(User).where(
        User.is_active.is_(True),
        (User.username == identifier) | (User.phone == identifier),
    ))
    password_hash = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
    password_matches = verify_password(password, password_hash)
    if user is None or not user.password_hash or not password_matches:
        return None
    return user


async def build_access_context(session: AsyncSession, user: User) -> AccessContext:
    permission_rows = await session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id, Role.is_active.is_(True))
    )
    permission_codes: set[PermissionCode] = set()
    for code in permission_rows:
        try:
            permission_codes.add(PermissionCode(code))
        except ValueError:
            continue

    scope_rows = list(
        await session.scalars(select(UserScope).where(UserScope.user_id == user.id))
    )
    scopes: dict[PermissionCode, list[Scope]] = {}
    for row in scope_rows:
        try:
            permission = PermissionCode(row.permission_code)
            kind = ScopeKind(row.scope_kind)
        except ValueError:
            continue
        scopes.setdefault(permission, []).append(
            Scope(kind, {row.scope_value} if row.scope_value is not None else set())
        )
    return AccessContext(user_id=user.id, permissions=permission_codes, scopes=scopes)


async def get_user_role_metadata(
    session: AsyncSession, user_id: int, *, active_only: bool = True
) -> list[dict[str, object]]:
    """Return role/work-group metadata for API clients.

    Permission links remain authoritative for authorization.  This helper is
    presentation metadata only, but it deliberately hides archived roles by
    default so a merged legacy role cannot create a second workbench section.
    """

    query = (
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.id)
    )
    if active_only:
        query = query.where(Role.is_active.is_(True))
    result: list[dict[str, object]] = []
    for role in await session.scalars(query):
        metadata = get_role_metadata(role.code)
        result.append({
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "is_active": bool(role.is_active),
            "work_group": role.work_group or (metadata.work_group if metadata else None),
            "description": role.description or (metadata.description if metadata else None),
            "operations": list(metadata.operations) if metadata else [],
        })
    return result
