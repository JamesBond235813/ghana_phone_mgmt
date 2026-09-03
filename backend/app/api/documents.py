from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import get_access_context, require_permission
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.db.models import ReceivingOrder, RepairOrder, ReturnOrder, SalesOrder, Shipment, StocktakeOrder, TransferOrder
from app.db.session import get_db

router = APIRouter(prefix="/documents", tags=["documents"])


def visible(context: AccessContext, organization_id: int | None, location_id: int | None) -> bool:
    return context.can_access(PermissionCode.PHONE_VIEW, organization_id=organization_id, location_id=location_id) or context.can_access(PermissionCode.REPORT_VIEW, organization_id=organization_id, location_id=location_id)


@router.get("")
async def list_documents(
    status: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(get_access_context),
) -> dict[str, object]:
    if not context.can(PermissionCode.PHONE_VIEW) and not context.can(PermissionCode.REPORT_VIEW):
        raise HTTPException(status_code=403, detail="没有单据查询权限")
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1 到 500 之间")
    rows: list[dict[str, object]] = []
    async def add(kind: str, order_no: str, state: object, organization_id: int | None, location_id: int | None, total: int, extra: dict[str, object] | None = None) -> None:
        if status and str(state) != status:
            return
        if visible(context, organization_id, location_id):
            rows.append({"type": kind, "no": order_no, "status": str(state), "organization_id": organization_id, "location_id": location_id, "total_count": total, **(extra or {})})

    for order in await session.scalars(select(Shipment).order_by(Shipment.id.desc()).limit(limit)):
        await add("shipment", order.shipment_no, order.status, order.origin_organization_id, order.origin_location_id, order.total_count, {"destination_location_id": order.destination_location_id})
    for order in await session.scalars(select(ReceivingOrder).order_by(ReceivingOrder.id.desc()).limit(limit)):
        await add("receiving", order.receiving_no, order.status, order.organization_id, order.location_id, order.expected_count, {"accepted_count": order.accepted_count, "exception_count": order.exception_count})
    for order in await session.scalars(select(TransferOrder).order_by(TransferOrder.id.desc()).limit(limit)):
        await add("transfer", order.transfer_no, order.status, order.source_organization_id, order.source_location_id, order.total_count, {"destination_location_id": order.destination_location_id, "received_count": order.received_count})
    for order in await session.scalars(select(SalesOrder).order_by(SalesOrder.id.desc()).limit(limit)):
        sales_extra: dict[str, object] = {}
        if context.can_access(PermissionCode.REPORT_VIEW, organization_id=order.organization_id, location_id=order.location_id):
            sales_extra["total_amount"] = str(order.total_amount) if order.total_amount is not None else None
        await add("sales", order.sales_no, order.status, order.organization_id, order.location_id, order.total_count, sales_extra)
    for order in await session.scalars(select(ReturnOrder).order_by(ReturnOrder.id.desc()).limit(limit)):
        await add("return", order.return_no, order.status, order.source_organization_id, order.source_location_id, order.total_count, {"destination_location_id": order.destination_location_id, "received_count": order.received_count})
    for order in await session.scalars(select(RepairOrder).order_by(RepairOrder.id.desc()).limit(limit)):
        await add("repair", order.repair_no, order.status, order.organization_id, order.location_id, order.total_count, {"completed_count": order.completed_count, "accepted_count": order.accepted_count})
    for order in await session.scalars(select(StocktakeOrder).order_by(StocktakeOrder.id.desc()).limit(limit)):
        await add("stocktake", order.stocktake_no, order.status, order.organization_id, order.location_id, order.expected_count, {"found_count": order.found_count, "missing_count": order.missing_count, "extra_count": order.extra_count, "adjustment_status": order.adjustment_status})
    rows.sort(key=lambda row: row["no"], reverse=True)
    return {"items": rows[:limit], "count": min(len(rows), limit)}
