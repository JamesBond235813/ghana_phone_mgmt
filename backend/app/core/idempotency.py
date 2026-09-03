from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IdempotencyRecord


async def get_cached_response(
    session: AsyncSession, *, key: str | None, user_id: int, operation: str,
) -> dict | None:
    if not key:
        return None
    if len(key) > 128:
        raise ValueError("幂等键长度不能超过 128 个字符")
    record = await session.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key))
    if record is None:
        return None
    if record.user_id != user_id or record.operation != operation:
        raise ValueError("幂等键已经用于其他操作")
    return record.response


async def save_response(
    session: AsyncSession, *, key: str | None, user_id: int, operation: str,
    response: dict, status_code: int = 200,
) -> None:
    if key:
        session.add(IdempotencyRecord(
            key=key, user_id=user_id, operation=operation, response=response,
            status_code=status_code, created_at=datetime.now(timezone.utc),
        ))
