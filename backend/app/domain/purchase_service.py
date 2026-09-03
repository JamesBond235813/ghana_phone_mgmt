from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InventoryTransaction, Location, Organization, PhoneDevice, PurchaseItem, PurchaseOrder
from app.domain.enums import DocumentStatus, PhoneStatus
from app.domain.imei import is_valid_imei

from app.domain.container_service import DomainError
from app.domain.location_guard import require_active_location


def make_order_no() -> str:
    return f"PO-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"


async def create_purchase_receipt(
    session: AsyncSession,
    *,
    organization_id: int,
    location_id: int,
    operator_id: int,
    items: list[dict],
    supplier: str | None = None,
    note: str | None = None,
) -> PurchaseOrder:
    if not items:
        raise DomainError("采购入库至少需要一台手机")
    try:
        await require_active_location(session, location_id, organization_id)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc

    imeis = [str(item["imei"]).strip() for item in items]
    all_imeis = [value for item in items for value in (str(item["imei"]).strip(), str(item.get("imei2")).strip() if item.get("imei2") else None)]
    all_imeis = [value for value in all_imeis if value]
    if len(set(all_imeis)) != len(all_imeis):
        raise DomainError("本次入库包含重复 IMEI")
    for imei in all_imeis:
        if not is_valid_imei(imei):
            raise DomainError(f"IMEI 格式或校验位错误: {imei}")
        existing = await session.scalar(select(PhoneDevice).where((PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei)))
        if existing is not None:
            raise DomainError(f"IMEI 已存在: {imei}")

    order = PurchaseOrder(
        order_no=make_order_no(), organization_id=organization_id, supplier=supplier,
        status=DocumentStatus.COMPLETED, operator_id=operator_id, total_count=len(items), note=note,
    )
    session.add(order)
    await session.flush()
    for item in items:
        phone = PhoneDevice(
            imei=str(item["imei"]).strip(), imei2=item.get("imei2"), brand=item.get("brand"),
            model=item.get("model"), storage=item.get("storage"), color=item.get("color"),
            condition=item.get("condition"), battery_health=item.get("battery_health"),
            purchase_price=item.get("purchase_price"), status=PhoneStatus.SHENZHEN_STOCK,
            current_organization_id=organization_id, current_location_id=location_id,
        )
        session.add(phone)
        await session.flush()
        session.add(PurchaseItem(purchase_order_id=order.id, phone_id=phone.id, purchase_price=item.get("purchase_price")))
        session.add(InventoryTransaction(
            phone_id=phone.id, action="采购入库", from_status=None, to_status=str(PhoneStatus.SHENZHEN_STOCK),
            to_location_id=location_id, document_type="purchase", document_id=order.order_no,
            operator_id=operator_id,
        ))
    return order
