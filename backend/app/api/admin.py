from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import get_access_context
from app.core.access import AccessContext
from app.core.permissions import PermissionCode, ScopeKind
from app.core.roles import get_role_metadata
from app.core.security import hash_password
from app.db.models import Location, OperationAudit, Organization, Permission, Role, RolePermission, User, UserRole, UserScope
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


def require_global(context: AccessContext, permission: PermissionCode) -> None:
    if not context.can(permission) or not any(scope.kind == ScopeKind.ALL for scope in context.scopes.get(permission, [])):
        raise HTTPException(status_code=403, detail="需要该管理权限的全局数据范围")


class OrganizationInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    country: str = Field(min_length=1, max_length=64)


class LocationInput(BaseModel):
    organization_id: int
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    location_type: str = Field(min_length=1, max_length=32)


class OrganizationUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None


class LocationUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    location_type: str | None = Field(default=None, min_length=1, max_length=32)
    is_active: bool | None = None


class ScopeInput(BaseModel):
    permission_code: PermissionCode
    scope_kind: ScopeKind
    scope_value: str | None = Field(default=None, max_length=128)


class UserInput(BaseModel):
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    username: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    role_ids: list[int] = Field(default_factory=list)
    scopes: list[ScopeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_identifier(self) -> "UserInput":
        if not self.phone and not self.username:
            raise ValueError("手机号和用户名至少填写一个")
        if self.username and (not self.username.isascii() or not self.username.isalpha()):
            raise ValueError("用户名只能包含英文字母")
        return self


class RoleInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    permission_codes: list[PermissionCode] = Field(default_factory=list)
    work_group: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)


class RoleUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    permission_codes: list[PermissionCode] | None = None
    work_group: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    is_active: bool | None = None


class UserUpdateInput(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None
    role_ids: list[int] | None = None
    scopes: list[ScopeInput] | None = None


async def validate_user_grants(session: AsyncSession, context: AccessContext, role_ids: list[int] | None, scopes: list[ScopeInput] | None) -> None:
    if role_ids is not None:
        for role_id in role_ids:
            role = await session.get(Role, role_id)
            if role is None:
                raise HTTPException(status_code=400, detail=f"角色不存在: {role_id}")
            if not role.is_active:
                raise HTTPException(status_code=400, detail=f"角色已停用，不能分配: {role_id}")
            role_permissions = await session.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role_id)
            )
            for code in role_permissions:
                try:
                    permission = PermissionCode(code)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=f"角色包含未知权限: {code}") from exc
                if not context.can(permission):
                    raise HTTPException(status_code=403, detail=f"不能授予角色包含的权限: {role_id}")
    if scopes is not None:
        for scope in scopes:
            if not context.can(scope.permission_code) or not any(item.kind == ScopeKind.ALL for item in context.scopes.get(scope.permission_code, [])):
                raise HTTPException(status_code=403, detail=f"不能授予权限范围: {scope.permission_code}")


@router.get("/organizations")
async def organizations(session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> list[dict[str, object]]:
    require_global(context, PermissionCode.USER_MANAGE)
    return [{"id": row.id, "code": row.code, "name": row.name, "country": row.country, "is_active": row.is_active} for row in await session.scalars(select(Organization).order_by(Organization.id))]


@router.post("/organizations")
async def create_organization(payload: OrganizationInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.USER_MANAGE)
    row = Organization(**payload.model_dump())
    session.add(row); await session.flush()
    session.add(OperationAudit(user_id=context.user_id, action="创建组织", resource_type="organization", resource_id=str(row.id), payload=payload.model_dump(), created_at=datetime.now(timezone.utc)))
    await session.commit()
    return {"id": row.id, **payload.model_dump()}


@router.patch("/organizations/{organization_id}")
async def update_organization(organization_id: int, payload: OrganizationUpdateInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.USER_MANAGE)
    row = await session.get(Organization, organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="组织不存在")
    try:
        if payload.name is not None:
            row.name = payload.name
        if payload.is_active is not None:
            row.is_active = payload.is_active
        session.add(OperationAudit(user_id=context.user_id, action="更新组织", resource_type="organization", resource_id=str(row.id), payload=payload.model_dump(exclude_unset=True), created_at=datetime.now(timezone.utc)))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return {"id": row.id, "code": row.code, "name": row.name, "country": row.country, "is_active": row.is_active}


@router.get("/locations")
async def locations(session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> list[dict[str, object]]:
    require_global(context, PermissionCode.USER_MANAGE)
    return [{"id": row.id, "organization_id": row.organization_id, "code": row.code, "name": row.name, "location_type": row.location_type, "is_active": row.is_active} for row in await session.scalars(select(Location).order_by(Location.id))]


@router.post("/locations")
async def create_location(payload: LocationInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.USER_MANAGE)
    if await session.get(Organization, payload.organization_id) is None:
        raise HTTPException(status_code=400, detail="组织不存在")
    row = Location(**payload.model_dump()); session.add(row); await session.flush()
    session.add(OperationAudit(user_id=context.user_id, action="创建地点", resource_type="location", resource_id=str(row.id), payload=payload.model_dump(), created_at=datetime.now(timezone.utc)))
    await session.commit()
    return {"id": row.id, **payload.model_dump()}


@router.patch("/locations/{location_id}")
async def update_location(location_id: int, payload: LocationUpdateInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.USER_MANAGE)
    row = await session.get(Location, location_id)
    if row is None:
        raise HTTPException(status_code=404, detail="地点不存在")
    try:
        if payload.name is not None:
            row.name = payload.name
        if payload.location_type is not None:
            row.location_type = payload.location_type
        if payload.is_active is not None:
            row.is_active = payload.is_active
        session.add(OperationAudit(user_id=context.user_id, action="更新地点", resource_type="location", resource_id=str(row.id), payload=payload.model_dump(exclude_unset=True), created_at=datetime.now(timezone.utc)))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return {"id": row.id, "organization_id": row.organization_id, "code": row.code, "name": row.name, "location_type": row.location_type, "is_active": row.is_active}


@router.get("/permissions")
async def permissions(session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> list[dict[str, object]]:
    require_global(context, PermissionCode.ROLE_MANAGE)
    return [{"id": row.id, "code": row.code, "name": row.name} for row in await session.scalars(select(Permission).order_by(Permission.code))]


@router.get("/audits")
async def audits(
    action: str | None = None,
    resource_type: str | None = None,
    user_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(get_access_context),
) -> list[dict[str, object]]:
    require_global(context, PermissionCode.AUDIT_VIEW)
    query = select(OperationAudit).order_by(OperationAudit.id.desc()).limit(limit)
    if action:
        query = query.where(OperationAudit.action == action)
    if resource_type:
        query = query.where(OperationAudit.resource_type == resource_type)
    if user_id is not None:
        query = query.where(OperationAudit.user_id == user_id)
    return [{
        "id": row.id, "user_id": row.user_id, "action": row.action,
        "resource_type": row.resource_type, "resource_id": row.resource_id,
        "payload": row.payload, "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in await session.scalars(query)]


def _role_metadata_payload(role: Role) -> dict[str, object]:
    metadata = get_role_metadata(role.code)
    return {
        "is_active": bool(role.is_active),
        "work_group": role.work_group or (metadata.work_group if metadata else None),
        "description": role.description or (metadata.description if metadata else None),
        "operations": list(metadata.operations) if metadata else [],
        "legacy_codes": list(metadata.legacy_codes) if metadata else [],
    }


async def _role_permission_codes(session: AsyncSession, role_id: int) -> list[str]:
    return list(await session.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.code)
    ))


@router.post("/roles")
async def create_role(payload: RoleInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.ROLE_MANAGE)
    metadata = get_role_metadata(payload.code)
    role = Role(
        code=payload.code,
        name=payload.name,
        is_active=True,
        work_group=payload.work_group or (metadata.work_group if metadata else None),
        description=payload.description if payload.description is not None else (metadata.description if metadata else None),
    )
    session.add(role); await session.flush()
    permissions = list(await session.scalars(select(Permission).where(Permission.code.in_([str(code) for code in payload.permission_codes])))) if payload.permission_codes else []
    if len(permissions) != len(set(payload.permission_codes)):
        await session.rollback()
        raise HTTPException(status_code=400, detail="存在未注册的权限")
    if any(not context.can(PermissionCode(permission.code)) for permission in permissions):
        await session.rollback()
        raise HTTPException(status_code=403, detail="不能授予当前账号没有的权限")
    try:
        for permission in permissions: session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    result = {"id": role.id, "code": role.code, "name": role.name, "permission_codes": [row.code for row in permissions]}
    result.update(_role_metadata_payload(role))
    return result


@router.get("/roles")
async def roles(
    include_inactive: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(get_access_context),
) -> list[dict[str, object]]:
    if not (
        (context.can(PermissionCode.ROLE_MANAGE) and any(scope.kind == ScopeKind.ALL for scope in context.scopes.get(PermissionCode.ROLE_MANAGE, [])))
        or (context.can(PermissionCode.USER_MANAGE) and any(scope.kind == ScopeKind.ALL for scope in context.scopes.get(PermissionCode.USER_MANAGE, [])))
    ):
        raise HTTPException(status_code=403, detail="需要用户或角色管理权限的全局数据范围")
    role_query = select(Role).order_by(Role.id)
    if not include_inactive:
        role_query = role_query.where(Role.is_active.is_(True))
    result=[]
    for role in await session.scalars(role_query):
        codes = await _role_permission_codes(session, role.id)
        item = {"id": role.id, "code": role.code, "name": role.name, "permission_codes": codes}
        item.update(_role_metadata_payload(role))
        result.append(item)
    return result


@router.patch("/roles/{role_id}")
async def update_role(role_id: int, payload: RoleUpdateInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.ROLE_MANAGE)
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    permissions = []
    if payload.permission_codes is not None:
        permissions = list(await session.scalars(select(Permission).where(Permission.code.in_([str(code) for code in payload.permission_codes]))))
        if len(permissions) != len(set(payload.permission_codes)):
            raise HTTPException(status_code=400, detail="存在未注册的权限")
        if any(not context.can(PermissionCode(permission.code)) for permission in permissions):
            raise HTTPException(status_code=403, detail="不能授予当前账号没有的权限")
    try:
        if payload.is_active is False and role.is_active:
            assigned_active_user = await session.scalar(
                select(User.id)
                .join(UserRole, UserRole.user_id == User.id)
                .where(UserRole.role_id == role.id, User.is_active.is_(True))
            )
            if assigned_active_user is not None:
                raise HTTPException(status_code=409, detail="角色仍分配给启用用户，请先迁移用户后停用")
        if payload.name is not None:
            role.name = payload.name
        if payload.work_group is not None:
            role.work_group = payload.work_group
        if payload.description is not None:
            role.description = payload.description
        if payload.is_active is not None:
            role.is_active = payload.is_active
        if payload.permission_codes is not None:
            await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
            for permission in permissions:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
        session.add(OperationAudit(user_id=context.user_id, action="更新角色", resource_type="role", resource_id=str(role.id), payload=payload.model_dump(exclude_unset=True), created_at=datetime.now(timezone.utc)))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    result = {"id": role.id, "code": role.code, "name": role.name}
    result.update(_role_metadata_payload(role))
    return result


@router.post("/users")
async def create_user(payload: UserInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.USER_MANAGE)
    if payload.phone and await session.scalar(select(User).where(User.phone == payload.phone)) is not None:
        raise HTTPException(status_code=409, detail="手机号已存在")
    if payload.username and await session.scalar(select(User).where(User.username == payload.username)) is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(phone=payload.phone, username=payload.username, display_name=payload.display_name, password_hash=hash_password(payload.password), is_active=True)
    session.add(user); await session.flush()
    try:
        await validate_user_grants(session, context, payload.role_ids, payload.scopes)
        for role_id in payload.role_ids:
            session.add(UserRole(user_id=user.id, role_id=role_id))
        for scope in payload.scopes:
            session.add(UserScope(user_id=user.id, permission_code=scope.permission_code, scope_kind=scope.scope_kind, scope_value=scope.scope_value))
        session.add(OperationAudit(user_id=context.user_id, action="创建用户", resource_type="user", resource_id=str(user.id), payload={"phone": user.phone, "username": user.username, "display_name": user.display_name, "role_ids": payload.role_ids, "scopes": [scope.model_dump() for scope in payload.scopes]}, created_at=datetime.now(timezone.utc)))
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    return {"id": user.id, "username": user.username, "phone": user.phone, "display_name": user.display_name, "is_active": user.is_active}


@router.get("/users")
async def users(session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> list[dict[str, object]]:
    require_global(context, PermissionCode.USER_MANAGE)
    result = []
    for user in await session.scalars(select(User).order_by(User.id)):
        role_ids = list(await session.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)))
        scope_rows = list(await session.scalars(select(UserScope).where(UserScope.user_id == user.id).order_by(UserScope.id)))
        result.append({
            "id": user.id, "username": user.username, "phone": user.phone, "display_name": user.display_name,
            "is_active": user.is_active, "role_ids": role_ids,
            "scopes": [{
                "permission_code": row.permission_code,
                "scope_kind": row.scope_kind,
                "scope_value": row.scope_value,
            } for row in scope_rows],
        })
    return result


@router.patch("/users/{user_id}")
async def update_user(user_id: int, payload: UserUpdateInput, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(get_access_context)) -> dict[str, object]:
    require_global(context, PermissionCode.USER_MANAGE)
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user_id == context.user_id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    await validate_user_grants(session, context, payload.role_ids, payload.scopes)
    try:
        if payload.display_name is not None:
            user.display_name = payload.display_name
        if payload.password is not None:
            user.password_hash = hash_password(payload.password)
        if payload.is_active is not None:
            user.is_active = payload.is_active
        if payload.role_ids is not None:
            await session.execute(delete(UserRole).where(UserRole.user_id == user.id))
            for role_id in payload.role_ids:
                session.add(UserRole(user_id=user.id, role_id=role_id))
        if payload.scopes is not None:
            await session.execute(delete(UserScope).where(UserScope.user_id == user.id))
            for scope in payload.scopes:
                session.add(UserScope(user_id=user.id, permission_code=scope.permission_code, scope_kind=scope.scope_kind, scope_value=scope.scope_value))
        session.add(OperationAudit(user_id=context.user_id, action="更新用户", resource_type="user", resource_id=str(user.id), payload=payload.model_dump(exclude_unset=True), created_at=datetime.now(timezone.utc)))
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    role_ids = list(await session.scalars(select(UserRole.role_id).where(UserRole.user_id == user.id)))
    scope_rows = list(await session.scalars(select(UserScope).where(UserScope.user_id == user.id).order_by(UserScope.id)))
    return {
        "id": user.id, "phone": user.phone, "display_name": user.display_name,
        "is_active": user.is_active, "role_ids": role_ids,
        "scopes": [{"permission_code": row.permission_code, "scope_kind": row.scope_kind, "scope_value": row.scope_value} for row in scope_rows],
    }
