from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_permission
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.core.idempotency import get_cached_response, save_response
from app.db.session import get_db
from app.domain.stocktake_adjustment_service import adjust_stocktake
from app.domain.stocktake_service import create_stocktake
from app.db.models import StocktakeOrder
from sqlalchemy import select

router = APIRouter(prefix="/stocktakes", tags=["stocktakes"])


class StocktakeInput(BaseModel):
    organization_id: int
    location_id: int
    imeis: list[str] = Field(min_length=1)
    note: str | None = None


class StocktakeAdjustmentInput(BaseModel):
    imei: str = Field(min_length=15, max_length=15)
    decision: str
    target_status: str | None = None
    note: str | None = None


@router.post("", dependencies=[Depends(require_permission(PermissionCode.STOCKTAKE_SUBMIT))])
async def submit_stocktake(
    payload: StocktakeInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.STOCKTAKE_SUBMIT)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if not context.can_access(PermissionCode.STOCKTAKE_SUBMIT, location_id=payload.location_id):
        raise HTTPException(status_code=403, detail="没有该地点的盘点权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="stocktake_submit")
    if cached is not None:
        return cached
    try:
        order = await create_stocktake(
            session, organization_id=payload.organization_id, location_id=payload.location_id,
            operator_id=context.user_id, scanned_imeis=payload.imeis, note=payload.note,
        )
        result = {
            "stocktake_no": order.stocktake_no, "expected_count": order.expected_count,
            "found_count": order.found_count, "missing_count": order.missing_count,
            "extra_count": order.extra_count, "status": str(order.status),
        }
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="stocktake_submit", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/{stocktake_no}/adjust", dependencies=[Depends(require_permission(PermissionCode.STOCKTAKE_ADJUST))])
async def adjust(
    stocktake_no: str,
    payload: list[StocktakeAdjustmentInput],
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.STOCKTAKE_ADJUST)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    order = await session.scalar(select(StocktakeOrder).where(StocktakeOrder.stocktake_no == stocktake_no))
    if order is None:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    if not context.can_access(PermissionCode.STOCKTAKE_ADJUST, location_id=order.location_id):
        raise HTTPException(status_code=403, detail="没有该地点的盘点差异处理权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="stocktake_adjust")
    if cached is not None:
        return cached
    try:
        order = await adjust_stocktake(session, stocktake_no=stocktake_no, reviewer_id=context.user_id, adjustments=[item.model_dump() for item in payload])
        result = {"stocktake_no": order.stocktake_no, "adjustment_status": order.adjustment_status, "reviewer_id": order.reviewer_id}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="stocktake_adjust", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
