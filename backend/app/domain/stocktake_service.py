from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InventoryTransaction, PhoneDevice, StocktakeItem, StocktakeOrder
from app.domain.enums import DocumentStatus
from app.domain.location_guard import require_active_location
from app.domain.shipment_service import make_no


async def create_stocktake(
    session: AsyncSession, *, organization_id: int, location_id: int,
    operator_id: int, scanned_imeis: list[str], note: str | None = None,
) -> StocktakeOrder:
    await require_active_location(session, location_id, organization_id)
    scanned = list(dict.fromkeys(i.strip() for i in scanned_imeis if i.strip()))
    expected = list(await session.scalars(select(PhoneDevice).where(
        PhoneDevice.current_organization_id == organization_id,
        PhoneDevice.current_location_id == location_id,
    )))
    expected_by_imei = {alias: phone for phone in expected for alias in (phone.imei, phone.imei2) if alias}
    expected_ids = {phone.id for phone in expected}
    if not scanned:
        raise ValueError("盘点至少需要扫描一台手机")
    order = StocktakeOrder(
        stocktake_no=make_no("STK"), organization_id=organization_id, location_id=location_id,
        status=DocumentStatus.COMPLETED, operator_id=operator_id,
        expected_count=len(expected), found_count=0, missing_count=0, extra_count=0, note=note,
    )
    session.add(order)
    await session.flush()
    now = datetime.now(timezone.utc)
    for imei in scanned:
        phone = await session.scalar(select(PhoneDevice).where(
            (PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei)
        ))
        result = "FOUND" if imei in expected_by_imei else "EXTRA"
        session.add(StocktakeItem(
            stocktake_order_id=order.id, phone_id=phone.id if phone else None,
            imei_snapshot=imei, result=result, scanned_at=now,
        ))
        if phone and phone.id in expected_ids:
            order.found_count += 1
    order.missing_count = max(order.expected_count - order.found_count, 0)
    order.extra_count = sum(1 for imei in scanned if imei not in expected_by_imei)
    for phone in expected:
        if phone.imei not in scanned and (not phone.imei2 or phone.imei2 not in scanned):
            session.add(StocktakeItem(
                stocktake_order_id=order.id, phone_id=phone.id,
                imei_snapshot=phone.imei, result="MISSING", scanned_at=None,
            ))
    return order
