from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InventoryTransaction, StocktakeAdjustment, StocktakeItem, StocktakeOrder
from app.domain.container_service import find_phone_by_imei, remove_phone_from_tray
from app.domain.enums import PhoneStatus


async def adjust_stocktake(
    session: AsyncSession, *, stocktake_no: str, reviewer_id: int,
    adjustments: list[dict],
) -> StocktakeOrder:
    order = await session.scalar(select(StocktakeOrder).where(StocktakeOrder.stocktake_no == stocktake_no))
    if order is None:
        raise ValueError("盘点单不存在")
    if order.adjustment_status == "COMPLETED":
        return order
    if not adjustments:
        raise ValueError("至少需要一条差异处理意见")
    items = list(await session.scalars(select(StocktakeItem).where(StocktakeItem.stocktake_order_id == order.id)))
    by_imei = {item.imei_snapshot: item for item in items}
    seen_imeis: set[str] = set()
    now = datetime.now(timezone.utc)
    for data in adjustments:
        imei = str(data.get("imei", "")).strip()
        decision = str(data.get("decision", "")).upper()
        if imei in seen_imeis:
            continue
        seen_imeis.add(imei)
        item = by_imei.get(imei)
        if item is None:
            raise ValueError(f"IMEI 不属于该盘点单: {imei}")
        if item.result not in {"MISSING", "EXTRA"}:
            raise ValueError(f"该 IMEI 没有待处理差异: {imei}")
        existing = await session.scalar(select(StocktakeAdjustment).where(
            StocktakeAdjustment.stocktake_order_id == order.id,
            StocktakeAdjustment.imei_snapshot == imei,
        ))
        if existing is not None:
            continue
        phone = await find_phone_by_imei(session, imei)
        target_status = data.get("target_status")
        if decision == "CONFIRM_MISSING":
            if item.result != "MISSING" or phone is None:
                raise ValueError(f"只能确认盘点缺失手机: {imei}")
            old_status, old_location = str(phone.status), phone.current_location_id
            await remove_phone_from_tray(session, phone.imei, action="盘点确认缺失移出托盘")
            phone.status = PhoneStatus.FROZEN
            phone.current_organization_id = None
            phone.current_location_id = None
            session.add(InventoryTransaction(
                phone_id=phone.id, action="盘点确认缺失", from_status=old_status,
                to_status=str(PhoneStatus.FROZEN), from_location_id=old_location,
                to_location_id=None, document_type="stocktake", document_id=stocktake_no,
                operator_id=reviewer_id, note=data.get("note"),
            ))
        elif decision == "ACCEPT_EXTRA":
            if item.result != "EXTRA" or phone is None:
                raise ValueError(f"只能接收盘点多出手机: {imei}")
            if target_status not in {str(PhoneStatus.GHANA_STOCK), str(PhoneStatus.STORE_STOCK), str(PhoneStatus.AVAILABLE_AGAIN)}:
                raise ValueError("接收多出手机必须指定合法目标状态")
            old_status, old_location = str(phone.status), phone.current_location_id
            phone.status = PhoneStatus(target_status)
            phone.current_organization_id = order.organization_id
            phone.current_location_id = order.location_id
            session.add(InventoryTransaction(
                phone_id=phone.id, action="盘点接收多出", from_status=old_status,
                to_status=target_status, from_location_id=old_location,
                to_location_id=order.location_id, document_type="stocktake", document_id=stocktake_no,
                operator_id=reviewer_id, note=data.get("note"),
            ))
        elif decision != "IGNORE":
            raise ValueError(f"盘点差异处理方式不合法: {decision}")
        session.add(StocktakeAdjustment(
            stocktake_order_id=order.id, stocktake_item_id=item.id, imei_snapshot=imei,
            decision=decision, target_status=str(target_status) if target_status else None,
            note=data.get("note"), reviewer_id=reviewer_id, created_at=now,
        ))
    total_diff = order.missing_count + order.extra_count
    processed_count = await session.scalar(select(func.count(StocktakeAdjustment.id)).where(StocktakeAdjustment.stocktake_order_id == order.id))
    if total_diff == 0 or processed_count >= total_diff:
        order.adjustment_status = "COMPLETED"
        order.reviewer_id = reviewer_id
        order.reviewed_at = now
    return order
