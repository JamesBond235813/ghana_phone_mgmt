from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db


bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_subject(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        return decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


async def get_current_user(
    subject: str = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db),
) -> User:
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="用户标识无效") from exc
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user
