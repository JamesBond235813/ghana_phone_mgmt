from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.db.models import User
from app.db.session import get_db
from app.repositories.users import build_access_context
from sqlalchemy.ext.asyncio import AsyncSession


async def get_access_context(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AccessContext:
    return await build_access_context(session, user)


def require_permission(permission: PermissionCode):
    async def dependency(context: AccessContext = Depends(get_access_context)) -> AccessContext:
        if not context.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"没有权限: {permission}")
        return context

    return dependency
