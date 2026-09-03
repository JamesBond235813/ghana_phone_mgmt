from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_permission
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.core.idempotency import get_cached_response, save_response
from app.db.session import get_db
from app.db.models import ReceivingOrder
from sqlalchemy import select
from app.domain.enums import ContainerKind
from app.domain.shipment_service import dispatch_shipment, inspect_phone, start_receiving


router = APIRouter(prefix="/shipments", tags=["shipments"])


class ShipmentContainerInput(BaseModel):
    kind: ContainerKind
    code: str = Field(min_length=1, max_length=64)


class DispatchInput(BaseModel):
    origin_organization_id: int
    origin_location_id: int
    destination_organization_id: int
    destination_location_id: int
    logistics_no: str | None = None
    containers: list[ShipmentContainerInput] = Field(min_length=1)


class ReceivingStartInput(BaseModel):
    shipment_no: str
    organization_id: int
    location_id: int


class InspectInput(BaseModel):
    receiving_no: str
    imei: str = Field(min_length=15, max_length=15)
    accepted: bool
    note: str | None = None
    target_tray_code: str | None = Field(default=None, min_length=1, max_length=64)
    target_box_code: str | None = Field(default=None, min_length=1, max_length=64)


@router.post("/dispatch")
async def dispatch(
    payload: DispatchInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.SHIPMENT_DISPATCH)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if not context.can_access(PermissionCode.SHIPMENT_DISPATCH, location_id=payload.origin_location_id):
        raise HTTPException(status_code=403, detail="没有起运地点的发运权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="shipment_dispatch")
    if cached is not None:
        return cached
    try:
        shipment = await dispatch_shipment(
            session,
            origin_organization_id=payload.origin_organization_id,
            origin_location_id=payload.origin_location_id,
            destination_organization_id=payload.destination_organization_id,
            destination_location_id=payload.destination_location_id,
            operator_id=context.user_id,
            containers=[(item.kind, item.code) for item in payload.containers],
            logistics_no=payload.logistics_no,
        )
        result = {"shipment_no": shipment.shipment_no, "total_count": shipment.total_count, "status": str(shipment.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="shipment_dispatch", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/receiving/start")
async def receive_start(
    payload: ReceivingStartInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.RECEIVING_UNPACK)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if not context.can_access(PermissionCode.RECEIVING_UNPACK, location_id=payload.location_id):
        raise HTTPException(status_code=403, detail="没有该接收地点的拆箱权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="receiving_start")
    if cached is not None:
        return cached
    try:
        receiving = await start_receiving(
            session, shipment_no=payload.shipment_no, organization_id=payload.organization_id,
            location_id=payload.location_id, operator_id=context.user_id,
        )
        result = {"receiving_no": receiving.receiving_no, "expected_count": receiving.expected_count, "status": str(receiving.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="receiving_start", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/receiving/inspect")
async def inspect(
    payload: InspectInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.RECEIVING_ACCEPT)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    receiving = await session.scalar(
        select(ReceivingOrder).where(ReceivingOrder.receiving_no == payload.receiving_no)
    )
    if receiving is None:
        raise HTTPException(status_code=404, detail="验收单不存在")
    if not context.can_access(PermissionCode.RECEIVING_ACCEPT, location_id=receiving.location_id):
        raise HTTPException(status_code=403, detail="没有该接收地点的验收权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="receiving_inspect")
    if cached is not None:
        return cached
    try:
        receiving = await inspect_phone(
            session, receiving_no=payload.receiving_no, imei=payload.imei,
            accepted=payload.accepted, checker_id=context.user_id, note=payload.note,
            target_tray_code=payload.target_tray_code, target_box_code=payload.target_box_code,
        )
        result = {
            "receiving_no": receiving.receiving_no, "accepted_count": receiving.accepted_count,
            "exception_count": receiving.exception_count, "expected_count": receiving.expected_count,
            "status": str(receiving.status),
        }
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="receiving_inspect", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
