from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_permission
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.core.idempotency import get_cached_response, save_response
from app.db.models import RepairOrder
from app.db.session import get_db
from app.domain.enums import ContainerKind
from app.domain.repair_service import accept_repair_order, accept_repair, complete_repair, create_repair_order


router = APIRouter(prefix="/repairs", tags=["repairs"])


class RepairContainerInput(BaseModel):
    kind: ContainerKind
    code: str = Field(min_length=1, max_length=64)


class RepairCreateInput(BaseModel):
    organization_id: int
    location_id: int
    imeis: list[str] = Field(default_factory=list)
    return_no: str | None = None
    containers: list[RepairContainerInput] = Field(default_factory=list)
    note: str | None = None


class RepairCompleteInput(BaseModel):
    repair_no: str
    imei: str = Field(min_length=15, max_length=15)
    fault_description: str | None = None
    diagnosis: str | None = None
    work_done: str | None = None
    parts: list = Field(default_factory=list)
    repair_cost: Decimal | None = Field(default=None, ge=0)
    repair_result: str = "REPAIRED"


class RepairAcceptInput(BaseModel):
    repair_no: str
    imei: str = Field(min_length=15, max_length=15)
    disposition: str


@router.post("")
async def create_repair(
    payload: RepairCreateInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.REPAIR_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if not context.can_access(PermissionCode.REPAIR_CREATE, location_id=payload.location_id):
        raise HTTPException(status_code=403, detail="没有该维修地点的建单权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_create")
    if cached is not None:
        return cached
    try:
        order = await create_repair_order(
            session, organization_id=payload.organization_id, location_id=payload.location_id,
            operator_id=context.user_id, imeis=payload.imeis, return_no=payload.return_no,
            containers=[(item.kind, item.code) for item in payload.containers] or None, note=payload.note,
        )
        result = {"repair_no": order.repair_no, "total_count": order.total_count, "status": str(order.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_create", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/{repair_no}/accept")
async def technician_accept(
    repair_no: str,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.REPAIR_RECEIVE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    order = await session.scalar(select(RepairOrder).where(RepairOrder.repair_no == repair_no))
    if order is None:
        raise HTTPException(status_code=404, detail="维修单不存在")
    if not context.can_access(PermissionCode.REPAIR_RECEIVE, location_id=order.location_id):
        raise HTTPException(status_code=403, detail="没有该维修地点的接收权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_accept")
    if cached is not None:
        return cached
    try:
        order = await accept_repair_order(session, repair_no=repair_no, technician_id=context.user_id)
        result = {"repair_no": order.repair_no, "status": str(order.status), "technician_id": order.technician_id}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_accept", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/{repair_no}/complete")
async def technician_complete(
    repair_no: str,
    payload: RepairCompleteInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.REPAIR_UPDATE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if payload.repair_no != repair_no:
        raise HTTPException(status_code=400, detail="路径维修单号与请求体不一致")
    order = await session.scalar(select(RepairOrder).where(RepairOrder.repair_no == repair_no))
    if order is None:
        raise HTTPException(status_code=404, detail="维修单不存在")
    if not context.can_access(PermissionCode.REPAIR_UPDATE, location_id=order.location_id):
        raise HTTPException(status_code=403, detail="没有该维修地点的操作权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_complete")
    if cached is not None:
        return cached
    try:
        order = await complete_repair(
            session, repair_no=repair_no, imei=payload.imei, technician_id=context.user_id,
            fault_description=payload.fault_description, diagnosis=payload.diagnosis,
            work_done=payload.work_done, parts=payload.parts, repair_cost=payload.repair_cost,
            repair_result=payload.repair_result,
        )
        result = {"repair_no": order.repair_no, "completed_count": order.completed_count, "status": str(order.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_complete", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/{repair_no}/review")
async def review_repair(
    repair_no: str,
    payload: RepairAcceptInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.REPAIR_APPROVE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if payload.repair_no != repair_no:
        raise HTTPException(status_code=400, detail="路径维修单号与请求体不一致")
    order = await session.scalar(select(RepairOrder).where(RepairOrder.repair_no == repair_no))
    if order is None:
        raise HTTPException(status_code=404, detail="维修单不存在")
    if not context.can_access(PermissionCode.REPAIR_APPROVE, location_id=order.location_id):
        raise HTTPException(status_code=403, detail="没有该维修地点的验收权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_review")
    if cached is not None:
        return cached
    try:
        order = await accept_repair(
            session, repair_no=repair_no, imei=payload.imei,
            disposition=payload.disposition, accepter_id=context.user_id,
        )
        result = {"repair_no": order.repair_no, "accepted_count": order.accepted_count, "status": str(order.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="repair_review", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
