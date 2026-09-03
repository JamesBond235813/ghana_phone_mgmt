from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_permission
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.core.idempotency import get_cached_response, save_response
from app.db.session import get_db
from app.domain.enums import ContainerKind
from app.domain.transfer_service import create_transfer, receive_transfer


router = APIRouter(prefix="/transfers", tags=["transfers"])


class TransferContainerInput(BaseModel):
    kind: ContainerKind
    code: str = Field(min_length=1, max_length=64)


class TransferCreateInput(BaseModel):
    source_organization_id: int
    source_location_id: int
    destination_organization_id: int
    destination_location_id: int
    containers: list[TransferContainerInput] = Field(min_length=1)


class TransferReceiveInput(BaseModel):
    transfer_no: str
    received_imeis: list[str] = Field(default_factory=list)
    complete: bool = False


@router.post("/issue")
async def issue_transfer(
    payload: TransferCreateInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.TRANSFER_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    if not context.can_access(PermissionCode.TRANSFER_CREATE, location_id=payload.source_location_id):
        raise HTTPException(status_code=403, detail="没有来源地点的调拨出库权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="transfer_issue")
    if cached is not None:
        return cached
    try:
        transfer = await create_transfer(
            session,
            source_organization_id=payload.source_organization_id,
            source_location_id=payload.source_location_id,
            destination_organization_id=payload.destination_organization_id,
            destination_location_id=payload.destination_location_id,
            operator_id=context.user_id,
            containers=[(item.kind, item.code) for item in payload.containers],
        )
        result = {"transfer_no": transfer.transfer_no, "total_count": transfer.total_count, "status": str(transfer.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="transfer_issue", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/receive")
async def receive_transfer_endpoint(
    payload: TransferReceiveInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.TRANSFER_RECEIVE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    from sqlalchemy import select
    from app.db.models import TransferOrder

    transfer = await session.scalar(select(TransferOrder).where(TransferOrder.transfer_no == payload.transfer_no))
    if transfer is None:
        raise HTTPException(status_code=404, detail="调拨单不存在")
    if not context.can_access(PermissionCode.TRANSFER_RECEIVE, location_id=transfer.destination_location_id):
        raise HTTPException(status_code=403, detail="没有目标地点的调拨收货权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="transfer_receive")
    if cached is not None:
        return cached
    try:
        transfer = await receive_transfer(
            session, transfer_no=payload.transfer_no, received_imeis=payload.received_imeis,
            operator_id=context.user_id, complete=payload.complete,
        )
        result = {
            "transfer_no": transfer.transfer_no, "total_count": transfer.total_count,
            "received_count": transfer.received_count, "exception_count": transfer.exception_count,
            "status": str(transfer.status),
        }
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="transfer_receive", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
