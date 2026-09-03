from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Location, Organization


async def require_active_location(session: AsyncSession, location_id: int, organization_id: int | None = None) -> Location:
    location = await session.scalar(select(Location).where(Location.id == location_id))
    if location is None or not location.is_active:
        raise ValueError("地点不存在或已停用")
    if organization_id is not None and location.organization_id != organization_id:
        raise ValueError("地点不属于指定组织")
    organization = await session.get(Organization, location.organization_id)
    if organization is None or not organization.is_active:
        raise ValueError("所属组织不存在或已停用")
    return location
