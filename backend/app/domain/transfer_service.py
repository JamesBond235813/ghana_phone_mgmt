from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Box,
    InventoryTransaction,
    Location,
    PhoneDevice,
    TransferContainer,
    TransferItem,
    TransferOrder,
    Tray,
)
from app.domain.container_service import (
    DomainError,
    expand_container,
    remove_phone_from_tray,
    remove_tray_from_box,
)
from app.domain.enums import ContainerKind, DocumentStatus, PhoneStatus
from app.domain.shipment_service import make_no
from app.domain.location_guard import require_active_location


async def create_transfer(
    session: AsyncSession,
    *,
    source_organization_id: int,
    source_location_id: int,
    destination_organization_id: int,
    destination_location_id: int,
    operator_id: int,
    containers: list[tuple[ContainerKind, str]],
) -> TransferOrder:
    if not containers:
        raise DomainError("调拨至少需要一个手机、托盘或箱子")
    try:
        await require_active_location(session, source_location_id, source_organization_id)
        await require_active_location(session, destination_location_id, destination_organization_id)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    if source_location_id == destination_location_id:
        raise DomainError("来源地点和目标地点不能相同")

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
            selected_tray_ids.update(await session.scalars(select(Tray.id).where(Tray.current_box_id == box.id)))
        for phone in await expand_container(session, kind, code):
            phone_map[phone.id] = phone
    if not phone_map:
        raise DomainError("调拨对象中没有手机")
    allowed_statuses = {PhoneStatus.GHANA_STOCK, PhoneStatus.STORE_STOCK, PhoneStatus.AVAILABLE_AGAIN}
    for phone in phone_map.values():
        if phone.current_organization_id != source_organization_id or phone.current_location_id != source_location_id:
            raise DomainError(f"手机不在来源库存: {phone.imei}")
        if phone.status not in allowed_statuses:
            raise DomainError(f"手机当前状态不能调拨: {phone.imei} / {phone.status}")

    source_tray_by_phone = {phone.id: phone.current_tray_id for phone in phone_map.values()}
    source_box_by_phone: dict[int, int | None] = {}
    for phone in phone_map.values():
        tray = await session.get(Tray, phone.current_tray_id) if phone.current_tray_id else None
        source_box_by_phone[phone.id] = tray.current_box_id if tray else None

    transfer = TransferOrder(
        transfer_no=make_no("TRF-GH"), source_organization_id=source_organization_id,
        source_location_id=source_location_id, destination_organization_id=destination_organization_id,
        destination_location_id=destination_location_id, status=DocumentStatus.IN_TRANSIT,
        operator_id=operator_id, total_count=len(phone_map),
    )
    session.add(transfer)
    await session.flush()
    for kind, code in dict.fromkeys(containers):
        session.add(TransferContainer(transfer_order_id=transfer.id, container_kind=str(kind), container_code=code))

    trays = {tray.id: tray for tray in await session.scalars(select(Tray))}
    for tray_id in selected_tray_ids:
        tray = trays.get(tray_id)
        if tray and tray.current_box_id and tray.current_box_id not in selected_box_ids:
            await remove_tray_from_box(session, tray.code, action="调拨出库取出托盘")
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
            await remove_phone_from_tray(session, phone.imei, action="调拨出库取出手机")
        old_status = str(phone.status)
        phone.status = PhoneStatus.TRANSFERRING
        phone.current_location_id = None
        session.add(
            TransferItem(
                transfer_order_id=transfer.id, phone_id=phone.id, imei_snapshot=phone.imei,
                source_tray_id=source_tray_id, source_box_id=source_box_id,
            )
        )
        session.add(
            InventoryTransaction(
                phone_id=phone.id, action="调拨出库", from_status=old_status,
                to_status=str(PhoneStatus.TRANSFERRING), from_location_id=source_location_id,
                from_tray_id=source_tray_id, from_box_id=source_box_id,
                document_type="transfer", document_id=transfer.transfer_no,
                operator_id=operator_id,
            )
        )
    return transfer


async def receive_transfer(
    session: AsyncSession,
    *,
    transfer_no: str,
    received_imeis: list[str],
    operator_id: int,
    complete: bool,
) -> TransferOrder:
    transfer = await session.scalar(select(TransferOrder).where(TransferOrder.transfer_no == transfer_no))
    if transfer is None or transfer.status not in {DocumentStatus.IN_TRANSIT, DocumentStatus.RECEIVING}:
        raise DomainError("调拨单不存在或当前不能收货")
    transfer.status = DocumentStatus.RECEIVING
    items = list(await session.scalars(select(TransferItem).where(TransferItem.transfer_order_id == transfer.id)))
    item_by_imei = {item.imei_snapshot: item for item in items}
    if len(set(received_imeis)) != len(received_imeis):
        raise DomainError("收货列表包含重复 IMEI")
    for imei in received_imeis:
        item = item_by_imei.get(imei)
        if item is None:
            raise DomainError(f"IMEI 不属于当前调拨单: {imei}")
        if item.received_at is not None:
            continue
        phone = await session.get(PhoneDevice, item.phone_id)
        if phone is None:
            raise DomainError(f"手机记录不存在: {imei}")
        item.received_at = datetime.now(timezone.utc)
        phone.status = PhoneStatus.STORE_STOCK
        phone.current_organization_id = transfer.destination_organization_id
        phone.current_location_id = transfer.destination_location_id
        transfer.received_count += 1
        session.add(
            InventoryTransaction(
                phone_id=phone.id, action="门店调拨收货",
                from_status=str(PhoneStatus.TRANSFERRING), to_status=str(PhoneStatus.STORE_STOCK),
                to_location_id=transfer.destination_location_id, document_type="transfer",
                document_id=transfer.transfer_no, operator_id=operator_id,
            )
        )

    if complete:
        missing_items = [item for item in items if item.received_at is None]
        for item in missing_items:
            phone = await session.get(PhoneDevice, item.phone_id)
            if phone:
                await remove_phone_from_tray(session, phone.imei, action="门店收货短少移出容器")
                phone.status = PhoneStatus.FROZEN
                phone.current_organization_id = transfer.destination_organization_id
                phone.current_location_id = None
                session.add(
                    InventoryTransaction(
                        phone_id=phone.id, action="门店收货短少",
                        from_status=str(PhoneStatus.TRANSFERRING), to_status=str(PhoneStatus.FROZEN),
                        document_type="transfer", document_id=transfer.transfer_no,
                        operator_id=operator_id,
                    )
                )
        transfer.exception_count = len(missing_items)
        transfer.status = DocumentStatus.PARTIAL if missing_items else DocumentStatus.COMPLETED
        container_rows = list(
            await session.scalars(select(TransferContainer).where(TransferContainer.transfer_order_id == transfer.id))
        )
        box_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.BOX}
        tray_codes = {row.container_code for row in container_rows if row.container_kind == ContainerKind.TRAY}
        boxes = list(await session.scalars(select(Box).where(Box.code.in_(box_codes)))) if box_codes else []
        box_ids = {box.id for box in boxes}
        implicit_trays = list(await session.scalars(select(Tray).where(Tray.current_box_id.in_(box_ids)))) if box_ids else []
        explicit_trays = list(await session.scalars(select(Tray).where(Tray.code.in_(tray_codes)))) if tray_codes else []
        for tray in {tray.id: tray for tray in [*implicit_trays, *explicit_trays]}.values():
            tray.current_location_id = transfer.destination_location_id
        for box in boxes:
            box.current_location_id = transfer.destination_location_id
    return transfer
