from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InventoryTransaction,
    PhoneDevice,
    RepairContainer,
    RepairItem,
    RepairOrder,
    ReturnItem,
    ReturnOrder,
)
from app.domain.container_service import DomainError, expand_container
from app.domain.enums import ContainerKind, DocumentStatus, PhoneStatus
from app.domain.shipment_service import make_no
from app.domain.location_guard import require_active_location


async def create_repair_order(
    session: AsyncSession,
    *,
    organization_id: int,
    location_id: int,
    operator_id: int,
    imeis: list[str],
    return_no: str | None = None,
    containers: list[tuple[ContainerKind, str]] | None = None,
    note: str | None = None,
) -> RepairOrder:
    try:
        await require_active_location(session, location_id, organization_id)
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    if containers:
        selected: dict[str, PhoneDevice] = {}
        for kind, code in containers:
            for phone in await expand_container(session, kind, code):
                selected[phone.imei] = phone
        imeis = list(dict.fromkeys([*imeis, *selected]))
    if not imeis:
        raise DomainError("维修单至少需要一台手机")

    return_order = None
    if return_no:
        return_order = await session.scalar(select(ReturnOrder).where(ReturnOrder.return_no == return_no))
        if return_order is None or return_order.status != DocumentStatus.COMPLETED:
            raise DomainError("退回单不存在或尚未完成接收")
        if return_order.destination_organization_id != organization_id or return_order.destination_location_id != location_id:
            raise DomainError("维修地点与退回目的地不一致")

    phones: list[PhoneDevice] = []
    for imei in imeis:
        phone = await session.scalar(select(PhoneDevice).where((PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei)))
        if phone is None:
            raise DomainError(f"手机不存在: {imei}")
        if phone.current_organization_id != organization_id or phone.current_location_id != location_id:
            raise DomainError(f"手机不在维修地点: {imei}")
        if phone.status != PhoneStatus.WAITING_REPAIR:
            raise DomainError(f"手机当前不能送修: {imei} / {phone.status}")
        if return_order:
            matched = await session.scalar(
                select(ReturnItem).where(ReturnItem.return_order_id == return_order.id, ReturnItem.phone_id == phone.id)
            )
            if matched is None:
                raise DomainError(f"手机不属于指定退回单: {imei}")
        phones.append(phone)

    order = RepairOrder(
        repair_no=make_no("REP"), return_order_id=return_order.id if return_order else None,
        organization_id=organization_id, location_id=location_id,
        status=DocumentStatus.SUBMITTED, operator_id=operator_id, total_count=len(phones), note=note,
    )
    session.add(order)
    await session.flush()
    if containers:
        for kind, code in dict.fromkeys(containers):
            session.add(RepairContainer(repair_order_id=order.id, container_kind=str(kind), container_code=code))
    for phone in phones:
        session.add(RepairItem(repair_order_id=order.id, phone_id=phone.id, imei_snapshot=phone.imei))
        session.add(InventoryTransaction(
            phone_id=phone.id, action="创建送修单", from_status=str(phone.status), to_status=str(phone.status),
            from_location_id=location_id, to_location_id=location_id,
            document_type="repair", document_id=order.repair_no, operator_id=operator_id,
        ))
    return order


async def accept_repair_order(
    session: AsyncSession, *, repair_no: str, technician_id: int
) -> RepairOrder:
    order = await session.scalar(select(RepairOrder).where(RepairOrder.repair_no == repair_no))
    if order is None or order.status != DocumentStatus.SUBMITTED:
        raise DomainError("维修单不存在或已经被接收")
    items = list(await session.scalars(select(RepairItem).where(RepairItem.repair_order_id == order.id)))
    for item in items:
        phone = await session.get(PhoneDevice, item.phone_id)
        if phone is None or phone.status != PhoneStatus.WAITING_REPAIR:
            raise DomainError(f"手机当前不能接收维修: {item.imei_snapshot}")
        phone.status = PhoneStatus.REPAIRING
        session.add(InventoryTransaction(
            phone_id=phone.id, action="维修人员接收", from_status=str(PhoneStatus.WAITING_REPAIR),
            to_status=str(PhoneStatus.REPAIRING), from_location_id=order.location_id,
            to_location_id=order.location_id, document_type="repair", document_id=order.repair_no,
            operator_id=technician_id,
        ))
    order.technician_id = technician_id
    order.status = DocumentStatus.IN_PROGRESS
    return order


async def complete_repair(
    session: AsyncSession,
    *,
    repair_no: str,
    imei: str,
    technician_id: int,
    fault_description: str | None = None,
    diagnosis: str | None = None,
    work_done: str | None = None,
    parts: list | None = None,
    repair_cost: object | None = None,
    repair_result: str = "REPAIRED",
) -> RepairOrder:
    if repair_result not in {"REPAIRED", "UNREPAIRABLE", "NO_REPAIR"}:
        raise DomainError("维修结果不合法")
    order = await session.scalar(select(RepairOrder).where(RepairOrder.repair_no == repair_no))
    if order is None or order.status not in {DocumentStatus.IN_PROGRESS, DocumentStatus.PENDING_ACCEPTANCE}:
        raise DomainError("维修单不存在或当前不能填写维修结果")
    item = await session.scalar(
        select(RepairItem).join(PhoneDevice, PhoneDevice.id == RepairItem.phone_id).where(
            RepairItem.repair_order_id == order.id, (PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei)
        )
    )
    if item is None or item.completed_at is not None:
        raise DomainError("维修明细不存在或已经提交")
    phone = await session.get(PhoneDevice, item.phone_id)
    if phone is None or phone.status != PhoneStatus.REPAIRING:
        raise DomainError("手机当前不在维修中")
    item.fault_description = fault_description
    item.diagnosis = diagnosis
    item.work_done = work_done
    item.parts = parts
    item.repair_cost = repair_cost
    item.repair_result = repair_result
    item.completed_at = datetime.now(timezone.utc)
    item.completed_by = technician_id
    phone.status = PhoneStatus.REPAIR_PENDING_ACCEPTANCE
    order.completed_count += 1
    session.add(InventoryTransaction(
        phone_id=phone.id, action="维修完成待验收", from_status=str(PhoneStatus.REPAIRING),
        to_status=str(PhoneStatus.REPAIR_PENDING_ACCEPTANCE), to_location_id=order.location_id,
        document_type="repair", document_id=order.repair_no, operator_id=technician_id,
        note=repair_result,
    ))
    if order.completed_count == order.total_count:
        order.status = DocumentStatus.PENDING_ACCEPTANCE
    return order


async def accept_repair(
    session: AsyncSession,
    *,
    repair_no: str,
    imei: str,
    disposition: str,
    accepter_id: int,
) -> RepairOrder:
    if disposition not in {"AVAILABLE_AGAIN", "FROZEN", "SCRAPPED"}:
        raise DomainError("维修处置结果不合法")
    order = await session.scalar(select(RepairOrder).where(RepairOrder.repair_no == repair_no))
    if order is None or order.status != DocumentStatus.PENDING_ACCEPTANCE:
        raise DomainError("维修单不存在或尚未完成维修")
    item = await session.scalar(
        select(RepairItem).join(PhoneDevice, PhoneDevice.id == RepairItem.phone_id).where(
            RepairItem.repair_order_id == order.id, (PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei)
        )
    )
    if item is None or item.completed_at is None or item.accepted_at is not None:
        raise DomainError("维修明细不存在、未完成或已经验收")
    if item.completed_by == accepter_id:
        raise DomainError("维修人员不能验收自己完成的维修")
    if item.repair_result == "UNREPAIRABLE" and disposition == "AVAILABLE_AGAIN":
        raise DomainError("不可维修的手机不能直接恢复为可售")
    phone = await session.get(PhoneDevice, item.phone_id)
    if phone is None or phone.status != PhoneStatus.REPAIR_PENDING_ACCEPTANCE:
        raise DomainError("手机当前不能验收")
    item.disposition = disposition
    item.accepted_at = datetime.now(timezone.utc)
    item.accepted_by = accepter_id
    target_status = {
        "AVAILABLE_AGAIN": PhoneStatus.AVAILABLE_AGAIN,
        "FROZEN": PhoneStatus.FROZEN,
        "SCRAPPED": PhoneStatus.LOST_OR_SCRAPPED,
    }[disposition]
    phone.status = target_status
    order.accepted_count += 1
    if disposition != "AVAILABLE_AGAIN":
        order.exception_count += 1
    session.add(InventoryTransaction(
        phone_id=phone.id, action="维修结果验收", from_status=str(PhoneStatus.REPAIR_PENDING_ACCEPTANCE),
        to_status=str(target_status), to_location_id=order.location_id,
        document_type="repair", document_id=order.repair_no, operator_id=accepter_id,
        note=disposition,
    ))
    if order.accepted_count == order.total_count:
        order.status = DocumentStatus.COMPLETED
    return order
