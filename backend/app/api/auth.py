from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import get_access_context
from app.api.dependencies import get_current_user
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Location, Organization, User
from app.db.session import get_db
from app.repositories.users import authenticate_password, build_access_context, get_user_role_metadata


router = APIRouter(prefix="/auth", tags=["auth"])


class PasswordLoginRequest(BaseModel):
    identifier: str | None = Field(default=None, min_length=1, max_length=64)
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_identifier(self) -> "PasswordLoginRequest":
        if not self.identifier and not self.phone:
            raise ValueError("请输入手机号或用户名")
        return self


class SmsCodeRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=32)


class SmsLoginRequest(SmsCodeRequest):
    code: str = Field(min_length=4, max_length=12)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=64)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/password")
async def login_by_password(
    payload: PasswordLoginRequest, session: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    user = await authenticate_password(session, payload.identifier or payload.phone or "", payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="手机号或密码错误")
    role_metadata = await get_user_role_metadata(session, user.id)
    result: dict[str, object] = {
        "access_token": create_access_token(str(user.id)),
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "phone": user.phone, "display_name": user.display_name},
    }
    if role_metadata:
        result["user"]["roles"] = role_metadata
        result["user"]["role_codes"] = [str(item["code"]) for item in role_metadata]
        work_groups = sorted({str(item["work_group"]) for item in role_metadata if item.get("work_group")})
        result["user"]["work_groups"] = work_groups
        result["user"]["work_group"] = work_groups[0] if len(work_groups) == 1 else None
    return result


@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    if "display_name" not in payload.model_fields_set and "username" not in payload.model_fields_set:
        raise HTTPException(status_code=400, detail="没有需要更新的个人资料")
    if "username" in payload.model_fields_set:
        username = payload.username.strip() if payload.username else None
        if username and username != user.username:
            existing = await session.scalar(select(User).where(User.username == username, User.id != user.id))
            if existing:
                raise HTTPException(status_code=409, detail="用户名已被使用")
        user.username = username
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    await session.commit()
    await session.refresh(user)
    return {"id": user.id, "username": user.username, "phone": user.phone, "display_name": user.display_name}


@router.patch("/password", status_code=204)
async def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    if not user.password_hash or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码错误")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()


@router.post("/sms/send", status_code=202)
async def send_sms_code(_: SmsCodeRequest) -> dict[str, str]:
    return {"status": "accepted", "provider": "stub"}


@router.post("/sms", status_code=501)
async def login_by_sms(_: SmsLoginRequest) -> dict[str, str]:
    return {"status": "not_implemented", "message": "短信运营商适配器待接入"}


@router.get("/me")
async def current_user(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> dict[str, object]:
    context = await build_access_context(session, user)
    role_metadata = await get_user_role_metadata(session, user.id)
    result: dict[str, object] = {
        "id": user.id,
        "username": user.username,
        "phone": user.phone,
        "display_name": user.display_name,
        "permissions": sorted(str(permission) for permission in context.permissions),
        "scopes": {
            str(permission): [
                {"kind": str(scope.kind), "values": sorted(scope.values)} for scope in scopes
            ]
            for permission, scopes in context.scopes.items()
        },
    }
    # Keep the no-role response backward compatible for lightweight clients,
    # while exposing canonical role/work-group metadata for real operators.
    if role_metadata:
        result["roles"] = role_metadata
        result["role_codes"] = [str(item["code"]) for item in role_metadata]
        work_groups = sorted({str(item["work_group"]) for item in role_metadata if item.get("work_group")})
        result["work_groups"] = work_groups
        result["work_group"] = work_groups[0] if len(work_groups) == 1 else None
    return result


@router.get("/work-locations")
async def work_locations(
    permission: list[PermissionCode] = Query(default=[]),
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(get_access_context),
) -> list[dict[str, object]]:
    """Return active locations usable as a source or destination selector.

    No inventory is exposed here. Source permission checks remain enforced by
    every business endpoint; this endpoint only removes manual ID entry from
    the PWA and provides stable labels for selectors.
    """
    rows = list(await session.execute(
        select(Location, Organization)
        .join(Organization, Organization.id == Location.organization_id)
        .where(Location.is_active.is_(True), Organization.is_active.is_(True))
        .order_by(Organization.id, Location.id)
    ))
    selected = set(permission) or set(context.permissions)
    result = []
    for location, organization in rows:
        source_allowed = any(
            context.can_access(code, country=organization.country,
                               organization_id=organization.id, location_id=location.id)
            for code in selected
        ) if selected else False
        result.append({
            "id": location.id,
            "organization_id": organization.id,
            "organization_code": organization.code,
            "organization_name": organization.name,
            "country": organization.country,
            "code": location.code,
            "name": location.name,
            "location_type": location.location_type,
            "source_allowed": source_allowed,
        })
    return result
