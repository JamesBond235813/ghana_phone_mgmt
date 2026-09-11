from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import get_access_context, require_permission
from app.core.access import AccessContext
from app.core.permissions import PermissionCode
from app.core.idempotency import get_cached_response, save_response
from app.db.models import Box, InventoryTransaction, PhoneDevice, Tray
from app.db.session import get_db
from app.domain.container_service import add_phone_to_tray, expand_container, put_tray_in_box
from app.domain.enums import ContainerKind
from app.domain.purchase_service import create_purchase_receipt


router = APIRouter(prefix="/inventory", tags=["inventory"])


class PurchaseItemInput(BaseModel):
    imei: str = Field(min_length=15, max_length=15)
    imei2: str | None = Field(default=None, min_length=15, max_length=15)
    brand: str | None = None
    model: str | None = None
    storage: str | None = None
    color: str | None = None
    condition: str | None = None
    battery_health: int | None = Field(default=None, ge=0, le=100)
    purchase_price: Decimal | None = Field(default=None, ge=0)


class PurchaseReceiptInput(BaseModel):
    organization_id: int
    location_id: int
    supplier: str | None = None
    note: str | None = None
    items: list[PurchaseItemInput] = Field(min_length=1)


class TrayInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    location_id: int | None = None
    imeis: list[str] = Field(default_factory=list)


class BoxInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    location_id: int | None = None
    tray_codes: list[str] = Field(default_factory=list)


class PhoneListQuery(BaseModel):
    location_id: int | None = None
    organization_id: int | None = None
    status: str | None = None
    q: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


@router.post("/purchase-receipts", dependencies=[Depends(require_permission(PermissionCode.PURCHASE_CREATE))])
async def purchase_receipt(
    payload: PurchaseReceiptInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(get_access_context),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    # Purchase intake is a physical station operation.  Check both the
    # organization and the exact receiving location so an organization-level
    # grant cannot silently expand into every warehouse in that organization.
    if not context.can_access(
        PermissionCode.PURCHASE_CREATE,
        organization_id=payload.organization_id,
        location_id=payload.location_id,
    ):
        raise HTTPException(status_code=403, detail="没有该采购收货地点的入库权限")
    try:
        cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="purchase_receipt")
        if cached is not None:
            return cached
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        order = await create_purchase_receipt(
            session, organization_id=payload.organization_id, location_id=payload.location_id,
            operator_id=context.user_id, items=[item.model_dump() for item in payload.items],
            supplier=payload.supplier, note=payload.note,
        )
        result = {"order_no": order.order_no, "total_count": order.total_count, "status": str(order.status)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="purchase_receipt", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/trays")
async def create_tray(
    payload: TrayInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.TRAY_MANAGE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    tray = await session.scalar(select(Tray).where(Tray.code == payload.code))
    effective_location_id = payload.location_id or (tray.current_location_id if tray else None)
    if effective_location_id is None or not context.can_access(
        PermissionCode.TRAY_MANAGE, location_id=effective_location_id
    ):
        raise HTTPException(status_code=403, detail="没有该地点的托盘管理权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="tray_manage")
    if cached is not None:
        return cached
    if tray is None:
        tray = Tray(code=payload.code, current_location_id=payload.location_id)
        session.add(tray)
        await session.flush()
    elif payload.location_id is not None:
        tray.current_location_id = payload.location_id
    try:
        for imei in payload.imeis:
            # Operators may scan either label on a dual-SIM handset.  Keep
            # the location guard here, but resolve IMEI2 the same way as the
            # domain container helper and phone lookup endpoint.
            phone = await session.scalar(
                select(PhoneDevice).where((PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei))
            )
            if phone is None:
                raise ValueError(f"IMEI 不存在: {imei}")
            if phone.current_location_id != effective_location_id:
                raise ValueError(f"手机不在托盘所在地点: {imei}")
            await add_phone_to_tray(session, imei, payload.code)
        result = {"code": tray.code, "phone_count": len(await expand_container(session, ContainerKind.TRAY, tray.code))}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="tray_manage", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post("/boxes")
async def create_box(
    payload: BoxInput,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.BOX_MANAGE)),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> dict[str, object]:
    box = await session.scalar(select(Box).where(Box.code == payload.code))
    effective_location_id = payload.location_id or (box.current_location_id if box else None)
    if effective_location_id is None or not context.can_access(
        PermissionCode.BOX_MANAGE, location_id=effective_location_id
    ):
        raise HTTPException(status_code=403, detail="没有该地点的箱子管理权限")
    cached = await get_cached_response(session, key=idempotency_key, user_id=context.user_id, operation="box_manage")
    if cached is not None:
        return cached
    if box is None:
        box = Box(code=payload.code, current_location_id=payload.location_id)
        session.add(box)
        await session.flush()
    elif payload.location_id is not None:
        box.current_location_id = payload.location_id
    try:
        for tray_code in payload.tray_codes:
            tray = await session.scalar(select(Tray).where(Tray.code == tray_code))
            if tray is None:
                raise ValueError(f"托盘不存在: {tray_code}")
            if tray.current_location_id != effective_location_id:
                raise ValueError(f"托盘不在箱子所在地点: {tray_code}")
            await put_tray_in_box(session, tray_code, payload.code)
        result = {"code": box.code, "phone_count": len(await expand_container(session, ContainerKind.BOX, box.code)), "tray_count": len(payload.tray_codes)}
        await save_response(session, key=idempotency_key, user_id=context.user_id, operation="box_manage", response=result)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.get("/phones/{imei}")
async def get_phone(imei: str, session: AsyncSession = Depends(get_db), context: AccessContext = Depends(require_permission(PermissionCode.PHONE_VIEW))) -> dict[str, object]:
    phone = await session.scalar(select(PhoneDevice).where((PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei)))
    if phone is None:
        raise HTTPException(status_code=404, detail="手机不存在")
    if not context.can_access(PermissionCode.PHONE_VIEW, organization_id=phone.current_organization_id, location_id=phone.current_location_id):
        raise HTTPException(status_code=403, detail="没有该手机的查看权限")
    tray = await session.scalar(select(Tray).where(Tray.id == phone.current_tray_id)) if phone.current_tray_id else None
    box = await session.scalar(select(Box).where(Box.id == tray.current_box_id)) if tray and tray.current_box_id else None
    # Auto-increment ids reflect insertion timing, not necessarily the
    # physical sequence (a backfill/reconciliation may add an intermediate
    # event later).  Present the immutable audit timeline in event time order
    # and use the id only as a deterministic tie-breaker.
    transactions = list(await session.scalars(
        select(InventoryTransaction)
        .where(InventoryTransaction.phone_id == phone.id)
        .order_by(InventoryTransaction.created_at, InventoryTransaction.id)
    ))
    return {
        "imei": phone.imei, "brand": phone.brand, "model": phone.model, "storage": phone.storage,
        "status": str(phone.status), "organization_id": phone.current_organization_id,
        "location_id": phone.current_location_id, "tray_code": tray.code if tray else None,
        "box_code": box.code if box else None,
        "timeline": [
            {
                "action": item.action, "from_status": item.from_status, "to_status": item.to_status,
                "from_location_id": item.from_location_id, "to_location_id": item.to_location_id,
                "from_tray_id": item.from_tray_id, "to_tray_id": item.to_tray_id,
                "from_box_id": item.from_box_id, "to_box_id": item.to_box_id,
                "document_type": item.document_type, "document_id": item.document_id,
                "operator_id": item.operator_id, "note": item.note,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in transactions
        ],
    }


@router.get("/phones")
async def list_phones(
    location_id: int | None = None,
    organization_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
    context: AccessContext = Depends(require_permission(PermissionCode.PHONE_VIEW)),
) -> dict[str, object]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1 到 500 之间")
    query = select(PhoneDevice).order_by(PhoneDevice.id)
    if location_id is not None:
        query = query.where(PhoneDevice.current_location_id == location_id)
    if organization_id is not None:
        query = query.where(PhoneDevice.current_organization_id == organization_id)
    if status:
        query = query.where(PhoneDevice.status == status)
    if q:
        query = query.where((PhoneDevice.imei.like(f"%{q}%")) | (PhoneDevice.imei2.like(f"%{q}%")))
    phones = list(await session.scalars(query))
    visible = [phone for phone in phones if context.can_access(
        PermissionCode.PHONE_VIEW, organization_id=phone.current_organization_id,
        location_id=phone.current_location_id,
    )]
    visible = visible[:limit]
    return {
        "items": [
            {"imei": phone.imei, "imei2": phone.imei2, "brand": phone.brand, "model": phone.model,
             "status": str(phone.status), "organization_id": phone.current_organization_id,
             "location_id": phone.current_location_id, "tray_id": phone.current_tray_id}
            for phone in visible
        ],
        "count": len(visible),
    }
