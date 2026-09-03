from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_permission
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.core.idempotency import get_cached_response, save_response
from app.db.models import ReturnOrder, SalesOrder
from app.db.session import get_db
from app.domain.enums import ContainerKind
from app.domain.sales_service import cancel_sale, confirm_sale, create_return, create_sale, receive_return


router = APIRouter(tags=["sales"])


class SalesContainerInput(BaseModel):
    kind: ContainerKind
    code: str = Field(min_length=1, max_length=64)


class SaleInput(BaseModel):
    organization_id: int
    location_id: int
    sales_type: str
    customer_name: str | None = None
    containers: list[SalesContainerInput] = Field(min_length=1)
    prices: dict[str, Decimal | None] = Field(default_factory=dict)
    note: str | None = None


class ReturnInput(BaseModel):
    sales_no: str
    source_organization_id: int
    source_location_id: int
    destination_organization_id: int
    destination_location_id: int
    imeis: list[str] = Field(default_factory=list)
    containers: list[SalesContainerInput] = Field(default_factory=list)
    note: str | None = None


class ReturnReceiveInput(BaseModel):
    return_no: str
    received_imeis: list[str] = Field(min_length=1)


@router.post("/sales")
async def create_sales_order(
    payload: SaleInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.SALES_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if not context.can_access(PermissionCode.SALES_CREATE, location_id=payload.location_id):
        raise HTTPException(status_code=403, detail="没有该门店的销售权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="sales_create")
    if cached is not None:
        return cached
    try:
        sale = await create_sale(
            session, organization_id=payload.organization_id, location_id=payload.location_id,
            sales_type=payload.sales_type, operator_id=context.user_id,
            containers=[(item.kind, item.code) for item in payload.containers],
            customer_name=payload.customer_name, prices=payload.prices, note=payload.note,
        )
        result = {"sales_no": sale.sales_no, "total_count": sale.total_count, "status": str(sale.status), "total_amount": str(sale.total_amount) if sale.total_amount is not None else None}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="sales_create", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/sales/{sales_no}/confirm")
async def confirm_sales_order(
    sales_no: str,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.SALES_APPROVE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    existing = await session.scalar(select(SalesOrder).where(SalesOrder.sales_no == sales_no))
    if existing is not None:
        cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="sales_confirm")
        if cached is not None:
            return cached
    try:
        sale = await confirm_sale(session, sales_no=sales_no, approver_id=context.user_id)
        if not context.can_access(PermissionCode.SALES_APPROVE, location_id=sale.location_id):
            raise HTTPException(status_code=403, detail="没有该门店的销售审核权限")
        result = {"sales_no": sale.sales_no, "status": str(sale.status), "total_count": sale.total_count}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="sales_confirm", response=result)
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/sales/{sales_no}/cancel")
async def cancel_sales_order(
    sales_no: str,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.SALES_CANCEL)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    sale = await session.scalar(select(SalesOrder).where(SalesOrder.sales_no == sales_no))
    if sale is None:
        raise HTTPException(status_code=404, detail="销售单不存在")
    if not context.can_access(PermissionCode.SALES_CANCEL, location_id=sale.location_id):
        raise HTTPException(status_code=403, detail="没有该门店的销售取消权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="sales_cancel")
    if cached is not None:
        return cached
    try:
        sale = await cancel_sale(session, sales_no=sales_no, operator_id=context.user_id)
        result = {"sales_no": sale.sales_no, "status": str(sale.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="sales_cancel", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/returns")
async def create_return_order(
    payload: ReturnInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.RETURN_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if not context.can_access(PermissionCode.RETURN_CREATE, location_id=payload.source_location_id):
        raise HTTPException(status_code=403, detail="没有该门店的退回权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="return_create")
    if cached is not None:
        return cached
    try:
        order = await create_return(
            session, sales_no=payload.sales_no, source_organization_id=payload.source_organization_id,
            source_location_id=payload.source_location_id, destination_organization_id=payload.destination_organization_id,
            destination_location_id=payload.destination_location_id, operator_id=context.user_id,
            imeis=payload.imeis, containers=[(item.kind, item.code) for item in payload.containers] or None,
            note=payload.note,
        )
        result = {"return_no": order.return_no, "total_count": order.total_count, "status": str(order.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="return_create", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/returns/receive")
async def receive_return_order(
    payload: ReturnReceiveInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.RETURN_RECEIVE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    order = await session.scalar(select(ReturnOrder).where(ReturnOrder.return_no == payload.return_no))
    if order is None:
        raise HTTPException(status_code=404, detail="退回单不存在")
    if not context.can_access(PermissionCode.RETURN_RECEIVE, location_id=order.destination_location_id):
        raise HTTPException(status_code=403, detail="没有该管理处的退回接收权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="return_receive")
    if cached is not None:
        return cached
    try:
        order = await receive_return(
            session, return_no=payload.return_no, received_imeis=payload.received_imeis,
            operator_id=context.user_id,
        )
        result = {"return_no": order.return_no, "received_count": order.received_count, "total_count": order.total_count, "status": str(order.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="return_receive", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
