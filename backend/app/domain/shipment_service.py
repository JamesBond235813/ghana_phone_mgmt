from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Box,
    InventoryTransaction,
    Location,
    PhoneDevice,
    ReceivingItem,
    ReceivingOrder,
    Shipment,
    ShipmentContainer,
    ShipmentItem,
    Tray,
)
from app.domain.container_service import (
    DomainError,
    add_phone_to_tray,
    expand_container,
    remove_phone_from_tray,
    remove_tray_from_box,
    put_tray_in_box,
)
from app.domain.enums import ContainerKind, DocumentStatus, PhoneStatus
from app.domain.location_guard import require_active_location


def make_no(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"


async def dispatch_shipment(
    session: AsyncSession,
    *,
    origin_organization_id: int,
    origin_location_id: int,
    destination_organization_id: int,
    destination_location_id: int,
    operator_id: int,
    containers: list[tuple[ContainerKind, str]],
    logistics_no: str | None = None,
) -> Shipment:
    if not containers:
        raise DomainError("发运单至少需要一个手机、托盘或箱子")
    try:
        await require_active_location(session, origin_location_id, origin_organization_id)
        await require_active_location(session, destination_location_id, destination_organization_id)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc

    phone_map: dict[int, PhoneDevice] = {}
    selected_tray_ids: set[int] = set()
    selected_box_ids: set[int] = set()
    for kind, code in containers:
        if kind == ContainerKind.TRAY:
            tray = await session.scalar(select(Tray).where(Tray.code == code))
            if tray is None:
                raise DomainError(f"托盘不存在: {code}")
            selected_tray_ids.add(tray.id)
        elif kind == ContainerKind.BOX:
            box = await session.scalar(select(Box).where(Box.code == code))
            if box is None:
                raise DomainError(f"箱子不存在: {code}")
            selected_box_ids.add(box.id)
            selected_tray_ids.update(
                await session.scalars(select(Tray.id).where(Tray.current_box_id == box.id))
            )
        for phone in await expand_container(session, kind, code):
            phone_map[phone.id] = phone
    if not phone_map:
        raise DomainError("发运对象中没有手机")
    allowed = {PhoneStatus.SHENZHEN_STOCK, PhoneStatus.IN_TRAY, PhoneStatus.IN_BOX}
    for phone in phone_map.values():
        if phone.current_organization_id != origin_organization_id or phone.current_location_id != origin_location_id:
            raise DomainError(f"手机不属于当前起运库存: {phone.imei}")
        if phone.status not in allowed:
            raise DomainError(f"手机当前状态不能发运: {phone.imei} / {phone.status}")

    source_tray_by_phone = {phone.id: phone.current_tray_id for phone in phone_map.values()}
    source_box_by_phone: dict[int, int | None] = {}
    for phone in phone_map.values():
        source_tray = await session.get(Tray, phone.current_tray_id) if phone.current_tray_id else None
        source_box_by_phone[phone.id] = source_tray.current_box_id if source_tray else None

    shipment = Shipment(
        shipment_no=make_no("SHIP-SZ-GH"), origin_organization_id=origin_organization_id,
        origin_location_id=origin_location_id, destination_organization_id=destination_organization_id,
        destination_location_id=destination_location_id, status=DocumentStatus.IN_TRANSIT,
        logistics_no=logistics_no, operator_id=operator_id, total_count=len(phone_map),
    )
    session.add(shipment)
    await session.flush()
    for kind, code in dict.fromkeys(containers):
        session.add(
            ShipmentContainer(
                shipment_id=shipment.id, container_kind=str(kind), container_code=code,
            )
        )
    trays = {tray.id: tray for tray in await session.scalars(select(Tray))}
    # A tray shipped without its outer box must be removed from that box before
    # departure. A loose phone shipped without its tray must be detached too.
    for tray_id in selected_tray_ids:
        tray = trays.get(tray_id)
        if tray and tray.current_box_id and tray.current_box_id not in selected_box_ids:
            await remove_tray_from_box(session, tray.code, action="深圳发运取出托盘")
        if tray:
            tray.current_location_id = None
    for box_id in selected_box_ids:
        box = await session.get(Box, box_id)
        if box:
            box.current_location_id = None
    for phone in phone_map.values():
        source_tray_id = source_tray_by_phone[phone.id]
        source_box_id = source_box_by_phone[phone.id]
        if source_tray_id is not None and source_tray_id not in selected_tray_ids:
            await remove_phone_from_tray(session, phone.imei, action="深圳发运取出手机")
        old_status = str(phone.status)
        phone.status = PhoneStatus.IN_TRANSIT
        phone.current_location_id = None
        session.add(
            ShipmentItem(
                shipment_id=shipment.id, phone_id=phone.id, imei_snapshot=phone.imei,
                source_tray_id=source_tray_id, source_box_id=source_box_id,
            )
        )
        session.add(
            InventoryTransaction(
                phone_id=phone.id, action="深圳发运", from_status=old_status,
                to_status=str(PhoneStatus.IN_TRANSIT), from_location_id=origin_location_id,
                to_location_id=None, from_tray_id=source_tray_id,
                from_box_id=source_box_id, document_type="shipment",
                document_id=shipment.shipment_no, operator_id=operator_id,
            )
        )
    return shipment


async def start_receiving(
    session: AsyncSession,
    *,
    shipment_no: str,
    organization_id: int,
    location_id: int,
    operator_id: int,
) -> ReceivingOrder:
    shipment = await session.scalar(select(Shipment).where(Shipment.shipment_no == shipment_no))
    if shipment is None:
        raise DomainError("发运单不存在")
    if shipment.status != DocumentStatus.IN_TRANSIT:
        raise DomainError("发运单当前不能接收")
    if shipment.destination_organization_id != organization_id or shipment.destination_location_id != location_id:
        raise DomainError("接收组织或地点与发运目的地不一致")
    existing = await session.scalar(select(ReceivingOrder).where(ReceivingOrder.shipment_id == shipment.id))
    if existing is not None:
        return existing

    shipment_items = list(await session.scalars(select(ShipmentItem).where(ShipmentItem.shipment_id == shipment.id)))
    container_rows = list(
        await session.scalars(select(ShipmentContainer).where(ShipmentContainer.shipment_id == shipment.id))
    )
    shipped_box_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.BOX}
    shipped_tray_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.TRAY}
    shipped_boxes = list(await session.scalars(select(Box).where(Box.code.in_(shipped_box_codes)))) if shipped_box_codes else []
    shipped_box_ids = {box.id for box in shipped_boxes}
    implicit_trays = list(await session.scalars(select(Tray).where(Tray.current_box_id.in_(shipped_box_ids)))) if shipped_box_ids else []
    explicit_trays = list(await session.scalars(select(Tray).where(Tray.code.in_(shipped_tray_codes)))) if shipped_tray_codes else []
    shipped_trays = {tray.id: tray for tray in [*implicit_trays, *explicit_trays]}
    receiving = ReceivingOrder(
        receiving_no=make_no("RCV-GH"), shipment_id=shipment.id, organization_id=organization_id,
        location_id=location_id, status=DocumentStatus.RECEIVING, operator_id=operator_id,
        expected_count=len(shipment_items),
    )
    session.add(receiving)
    await session.flush()


    for shipment_item in shipment_items:
        phone = await session.get(PhoneDevice, shipment_item.phone_id)
        if phone is None:
            raise DomainError(f"发运手机记录不存在: {shipment_item.imei_snapshot}")
        await remove_phone_from_tray(session, phone.imei, action="加纳验收取出托盘")
        old_status = str(phone.status)
        phone.status = PhoneStatus.GHANA_PENDING_INSPECTION
        phone.current_organization_id = organization_id
        phone.current_location_id = location_id
        session.add(
            ReceivingItem(
                receiving_order_id=receiving.id, phone_id=phone.id,
                imei_snapshot=phone.imei,
            )
        )
        session.add(InventoryTransaction(
            phone_id=phone.id, action="加纳到货待验收", from_status=old_status,
            to_status=str(PhoneStatus.GHANA_PENDING_INSPECTION),
            to_location_id=location_id, document_type="receiving",
            document_id=receiving.receiving_no, operator_id=operator_id,
        ))
    for tray in shipped_trays.values():
        await remove_tray_from_box(session, tray.code, action="加纳接收拆箱")
        tray.current_location_id = location_id
    for box in shipped_boxes:
        box.current_location_id = location_id
    shipment.status = DocumentStatus.RECEIVING
    return receiving


async def inspect_phone(
    session: AsyncSession,
    *,
    receiving_no: str,
    imei: str,
    accepted: bool,
    checker_id: int,
    note: str | None = None,
    target_tray_code: str | None = None,
    target_box_code: str | None = None,
) -> ReceivingOrder:
    receiving = await session.scalar(select(ReceivingOrder).where(ReceivingOrder.receiving_no == receiving_no))
    if receiving is None or receiving.status not in {DocumentStatus.RECEIVING, DocumentStatus.PARTIAL}:
        raise DomainError("验收单不存在或当前不能验收")
    item = await session.scalar(
        select(ReceivingItem)
        .join(PhoneDevice, PhoneDevice.id == ReceivingItem.phone_id)
        .where(ReceivingItem.receiving_order_id == receiving.id, (PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei))
    )
    if item is None:
        raise DomainError("该 IMEI 不属于当前验收单")
    if item.checked_at is not None:
        raise DomainError("该手机已经验收")
    phone = await session.get(PhoneDevice, item.phone_id)
    if phone is None:
        raise DomainError("手机记录不存在")

    item.result = "正常" if accepted else "异常"
    item.note = note
    item.checked_at = datetime.now(timezone.utc)
    item.checker_id = checker_id
    old_status = str(phone.status)
    phone.status = PhoneStatus.GHANA_STOCK if accepted else PhoneStatus.FROZEN
    if accepted:
        if target_box_code and not target_tray_code:
            raise DomainError("重新装箱时必须同时指定托盘编号")
        if target_tray_code:
            tray = await session.scalar(select(Tray).where(Tray.code == target_tray_code))
            if tray is None:
                tray = Tray(code=target_tray_code, current_location_id=receiving.location_id)
                session.add(tray)
                await session.flush()
            elif tray.current_location_id != receiving.location_id:
                raise DomainError(f"目标托盘不在接收地点: {target_tray_code}")
            await add_phone_to_tray(session, phone.imei, target_tray_code, action="加纳验收重新装入托盘")
            if target_box_code:
                box = await session.scalar(select(Box).where(Box.code == target_box_code))
                if box is None:
                    box = Box(code=target_box_code, current_location_id=receiving.location_id)
                    session.add(box)
                    await session.flush()
                elif box.current_location_id != receiving.location_id:
                    raise DomainError(f"目标箱子不在接收地点: {target_box_code}")
                await put_tray_in_box(session, target_tray_code, target_box_code, action="加纳验收重新装入箱子")
        receiving.accepted_count += 1
    else:
        receiving.exception_count += 1
    session.add(
        InventoryTransaction(
            phone_id=phone.id, action="加纳验收通过" if accepted else "加纳验收异常",
            from_status=old_status, to_status=str(phone.status),
            to_location_id=receiving.location_id, document_type="receiving",
            document_id=receiving.receiving_no, operator_id=checker_id, note=note,
        )
    )
    completed_count = receiving.accepted_count + receiving.exception_count
    if completed_count == receiving.expected_count:
        receiving.status = DocumentStatus.PARTIAL if receiving.exception_count else DocumentStatus.COMPLETED
        shipment = await session.get(Shipment, receiving.shipment_id)
        if shipment:
            shipment.status = receiving.status
    return receiving
