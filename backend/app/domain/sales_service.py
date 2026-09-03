from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InventoryTransaction,
    Box,
    PhoneDevice,
    ReturnContainer,
    ReturnItem,
    ReturnOrder,
    SalesContainer,
    SalesItem,
    SalesOrder,
    Tray,
)
from app.domain.container_service import DomainError, expand_container, remove_phone_from_tray, remove_tray_from_box
from app.domain.enums import ContainerKind, DocumentStatus, PhoneStatus
from app.domain.shipment_service import make_no
from app.domain.location_guard import require_active_location


async def create_sale(
    session: AsyncSession,
    *,
    organization_id: int,
    location_id: int,
    sales_type: str,
    operator_id: int,
    containers: list[tuple[ContainerKind, str]],
    customer_name: str | None = None,
    prices: dict[str, Decimal | None] | None = None,
    note: str | None = None,
) -> SalesOrder:
    if sales_type not in {"RETAIL", "WHOLESALE"}:
        raise DomainError("销售类型必须是零售或批发")
    if not containers:
        raise DomainError("销售至少需要一个手机、托盘或箱子")
    try:
        await require_active_location(session, location_id, organization_id)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    phone_map: dict[int, PhoneDevice] = {}
    for kind, code in containers:
        for phone in await expand_container(session, kind, code):
            phone_map[phone.id] = phone
    if not phone_map:
        raise DomainError("销售对象中没有手机")
    for phone in phone_map.values():
        if phone.current_organization_id != organization_id or phone.current_location_id != location_id:
            raise DomainError(f"手机不在当前门店库存: {phone.imei}")
        if phone.status not in {PhoneStatus.STORE_STOCK, PhoneStatus.AVAILABLE_AGAIN}:
            raise DomainError(f"手机当前不能销售: {phone.imei} / {phone.status}")

    sale = SalesOrder(
        sales_no=make_no("SALE"), organization_id=organization_id, location_id=location_id,
        sales_type=sales_type, status=DocumentStatus.PENDING_CONFIRMATION,
        customer_name=customer_name, total_count=len(phone_map), operator_id=operator_id, note=note,
    )
    session.add(sale)
    await session.flush()
    for kind, code in dict.fromkeys(containers):
        session.add(SalesContainer(sales_order_id=sale.id, container_kind=str(kind), container_code=code))
    total = Decimal("0")
    for phone in phone_map.values():
        old_status = str(phone.status)
        phone.status = PhoneStatus.SALE_PENDING
        price = prices.get(phone.imei) if prices else None
        if price is not None:
            total += price
        source_tray = await session.get(Tray, phone.current_tray_id) if phone.current_tray_id else None
        session.add(SalesItem(
            sales_order_id=sale.id, phone_id=phone.id, imei_snapshot=phone.imei,
            sale_price=price, source_tray_id=phone.current_tray_id,
            source_box_id=source_tray.current_box_id if source_tray else None,
        ))
        session.add(InventoryTransaction(
            phone_id=phone.id, action="销售待确认", from_status=old_status,
            to_status=str(PhoneStatus.SALE_PENDING), from_location_id=location_id,
            to_location_id=location_id, document_type="sales", document_id=sale.sales_no,
            operator_id=operator_id,
        ))
    sale.total_amount = total
    return sale


async def confirm_sale(session: AsyncSession, *, sales_no: str, approver_id: int) -> SalesOrder:
    sale = await session.scalar(select(SalesOrder).where(SalesOrder.sales_no == sales_no))
    if sale is None or sale.status != DocumentStatus.PENDING_CONFIRMATION:
        raise DomainError("销售单不存在或当前不能确认")
    if sale.operator_id == approver_id:
        raise DomainError("制单人不能确认自己的销售单")
    items = list(await session.scalars(select(SalesItem).where(SalesItem.sales_order_id == sale.id)))
    container_rows = list(await session.scalars(select(SalesContainer).where(SalesContainer.sales_order_id == sale.id)))
    box_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.BOX}
    tray_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.TRAY}
    boxes = list(await session.scalars(select(Box).where(Box.code.in_(box_codes)))) if box_codes else []
    selected_box_ids = {box.id for box in boxes}
    explicit_trays = list(await session.scalars(select(Tray).where(Tray.code.in_(tray_codes)))) if tray_codes else []
    implicit_trays = list(await session.scalars(select(Tray).where(Tray.current_box_id.in_(selected_box_ids)))) if selected_box_ids else []
    selected_trays = {tray.id: tray for tray in [*explicit_trays, *implicit_trays]}
    for tray in explicit_trays:
        if tray.current_box_id and tray.current_box_id not in selected_box_ids:
            await remove_tray_from_box(session, tray.code, action="销售取出托盘")
    for tray in selected_trays.values():
        tray.current_location_id = None
    for box in boxes:
        box.current_location_id = None
    for item in items:
        phone = await session.get(PhoneDevice, item.phone_id)
        if phone is None or phone.status != PhoneStatus.SALE_PENDING:
            raise DomainError(f"销售明细状态已变化: {item.imei_snapshot}")
        if item.source_tray_id is not None and item.source_tray_id not in selected_trays:
            await remove_phone_from_tray(session, phone.imei, action="销售取出手机")
        phone.status = PhoneStatus.SOLD
        phone.current_organization_id = None
        phone.current_location_id = None
        session.add(InventoryTransaction(
            phone_id=phone.id, action="销售确认", from_status=str(PhoneStatus.SALE_PENDING),
            to_status=str(PhoneStatus.SOLD), from_location_id=sale.location_id,
            to_location_id=None, document_type="sales", document_id=sale.sales_no,
            operator_id=approver_id,
        ))
    sale.status = DocumentStatus.COMPLETED
    sale.approver_id = approver_id
    return sale


async def cancel_sale(session: AsyncSession, *, sales_no: str, operator_id: int) -> SalesOrder:
    sale = await session.scalar(select(SalesOrder).where(SalesOrder.sales_no == sales_no))
    if sale is None or sale.status != DocumentStatus.PENDING_CONFIRMATION:
        raise DomainError("销售单不存在或当前不能取消")
    items = list(await session.scalars(select(SalesItem).where(SalesItem.sales_order_id == sale.id)))
    for item in items:
        phone = await session.get(PhoneDevice, item.phone_id)
        if phone and phone.status == PhoneStatus.SALE_PENDING:
            phone.status = PhoneStatus.STORE_STOCK
            session.add(InventoryTransaction(
                phone_id=phone.id, action="取消销售", from_status=str(PhoneStatus.SALE_PENDING),
                to_status=str(PhoneStatus.STORE_STOCK), from_location_id=sale.location_id,
                to_location_id=sale.location_id, document_type="sales", document_id=sale.sales_no,
                operator_id=operator_id,
            ))
    sale.status = DocumentStatus.CANCELLED
    return sale


async def create_return(
    session: AsyncSession,
    *,
    sales_no: str,
    source_organization_id: int,
    source_location_id: int,
    destination_organization_id: int,
    destination_location_id: int,
    operator_id: int,
    imeis: list[str],
    containers: list[tuple[ContainerKind, str]] | None = None,
    note: str | None = None,
) -> ReturnOrder:
    sale = await session.scalar(select(SalesOrder).where(SalesOrder.sales_no == sales_no))
    if sale is None or sale.status != DocumentStatus.COMPLETED:
        raise DomainError("原销售单不存在或尚未完成")
    sold_items = list(await session.scalars(select(SalesItem).where(SalesItem.sales_order_id == sale.id)))
    sold_by_imei = {item.imei_snapshot: item for item in sold_items}
    if containers:
        expanded: dict[str, PhoneDevice] = {}
        for kind, code in containers:
            for phone in await expand_container(session, kind, code):
                expanded[phone.imei] = phone
        imeis = list(dict.fromkeys([*imeis, *expanded]))
    if not imeis:
        raise DomainError("退回至少需要一台手机")
    if len(set(imeis)) != len(imeis):
        raise DomainError("退回列表包含重复 IMEI")
    phones: list[PhoneDevice] = []
    for imei in imeis:
        item = sold_by_imei.get(imei)
        if item is None:
            raise DomainError(f"手机不属于原销售单: {imei}")
        phone = await session.get(PhoneDevice, item.phone_id)
        if phone is None or phone.status != PhoneStatus.SOLD:
            raise DomainError(f"手机当前不能退回: {imei}")
        phones.append(phone)
    if sale.organization_id != source_organization_id or sale.location_id != source_location_id:
        raise DomainError("退回来源必须是原销售门店")

    order = ReturnOrder(
        return_no=make_no("RET"), sales_order_id=sale.id,
        source_organization_id=source_organization_id, source_location_id=source_location_id,
        destination_organization_id=destination_organization_id, destination_location_id=destination_location_id,
        status=DocumentStatus.IN_TRANSIT, total_count=len(phones), operator_id=operator_id, note=note,
    )
    session.add(order)
    await session.flush()
    selected_tray_ids: set[int] = set()
    selected_box_ids: set[int] = set()
    if containers:
        for kind, code in dict.fromkeys(containers):
            session.add(ReturnContainer(return_order_id=order.id, container_kind=str(kind), container_code=code))
            if kind == ContainerKind.TRAY:
                tray = await session.scalar(select(Tray).where(Tray.code == code))
                if tray:
                    selected_tray_ids.add(tray.id)
            elif kind == ContainerKind.BOX:
                box = await session.scalar(select(Box).where(Box.code == code))
                if box:
                    selected_box_ids.add(box.id)
                    selected_tray_ids.update(await session.scalars(select(Tray.id).where(Tray.current_box_id == box.id)))
    for tray_id in selected_tray_ids:
        tray = await session.get(Tray, tray_id)
        if tray and tray.current_box_id and tray.current_box_id not in selected_box_ids:
            await remove_tray_from_box(session, tray.code, action="销售退回取出托盘")
        if tray:
            tray.current_location_id = None
    for box_id in selected_box_ids:
        box = await session.get(Box, box_id)
        if box:
            box.current_location_id = None
    for phone in phones:
        if phone.current_tray_id is not None and phone.current_tray_id not in selected_tray_ids:
            await remove_phone_from_tray(session, phone.imei, action="销售退回取出手机")
        phone.status = PhoneStatus.RETURN_PENDING_CHECK
        phone.current_organization_id = None
        phone.current_location_id = None
        session.add(ReturnItem(return_order_id=order.id, phone_id=phone.id, imei_snapshot=phone.imei))
        session.add(InventoryTransaction(
            phone_id=phone.id, action="销售退回发出", from_status=str(PhoneStatus.SOLD),
            to_status=str(PhoneStatus.RETURN_PENDING_CHECK), from_location_id=source_location_id,
            to_location_id=None, document_type="return", document_id=order.return_no, operator_id=operator_id,
        ))
    return order


async def receive_return(
    session: AsyncSession, *, return_no: str, received_imeis: list[str], operator_id: int,
) -> ReturnOrder:
    order = await session.scalar(select(ReturnOrder).where(ReturnOrder.return_no == return_no))
    if order is None or order.status not in {DocumentStatus.IN_TRANSIT, DocumentStatus.PARTIAL}:
        raise DomainError("退回单不存在或当前不能接收")
    items = list(await session.scalars(select(ReturnItem).where(ReturnItem.return_order_id == order.id)))
    item_by_imei = {item.imei_snapshot: item for item in items}
    if len(set(received_imeis)) != len(received_imeis):
        raise DomainError("退回收货列表包含重复 IMEI")
    for imei in received_imeis:
        item = item_by_imei.get(imei)
        if item is None:
            raise DomainError(f"IMEI 不属于当前退回单: {imei}")
        if item.received_at is not None:
            continue
        phone = await session.get(PhoneDevice, item.phone_id)
        if phone is None:
            raise DomainError(f"手机记录不存在: {imei}")
        item.received_at = datetime.now(timezone.utc)
        phone.status = PhoneStatus.WAITING_REPAIR
        phone.current_organization_id = order.destination_organization_id
        phone.current_location_id = order.destination_location_id
        order.received_count += 1
        session.add(InventoryTransaction(
            phone_id=phone.id, action="管理处接收销售退回",
            from_status=str(PhoneStatus.RETURN_PENDING_CHECK), to_status=str(PhoneStatus.WAITING_REPAIR),
            to_location_id=order.destination_location_id, document_type="return", document_id=order.return_no,
            operator_id=operator_id,
        ))
    if order.received_count == order.total_count:
        order.status = DocumentStatus.COMPLETED
        container_rows = list(await session.scalars(select(ReturnContainer).where(ReturnContainer.return_order_id == order.id)))
        box_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.BOX}
        tray_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.TRAY}
        boxes = list(await session.scalars(select(Box).where(Box.code.in_(box_codes)))) if box_codes else []
        box_ids = {box.id for box in boxes}
        trays = list(await session.scalars(select(Tray).where(Tray.code.in_(tray_codes)))) if tray_codes else []
        implicit_trays = list(await session.scalars(select(Tray).where(Tray.current_box_id.in_(box_ids)))) if box_ids else []
        for tray in {tray.id: tray for tray in [*trays, *implicit_trays]}.values():
            tray.current_location_id = order.destination_location_id
        for box in boxes:
            box.current_location_id = order.destination_location_id
    return order
