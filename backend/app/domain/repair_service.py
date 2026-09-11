from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Box,
    InventoryTransaction,
    Location,
    PhoneDevice,
    RepairContainer,
    RepairItem,
    RepairOrder,
    ReturnItem,
    ReturnOrder,
    Tray,
)
from app.domain.container_service import DomainError, expand_container, remove_phone_from_tray
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
    # Keep the caller's physical scan order for audit snapshots while using a
    # de-duplicated set for expansion.  A box/tray is a source container in a
    # Ghana return hand-off; it is not the destination repair container.
    container_inputs = list(dict.fromkeys(containers or []))
    expanded_containers: list[tuple[ContainerKind, str, list[PhoneDevice]]] = []
    if containers:
        selected: dict[str, PhoneDevice] = {}
        for kind, code in container_inputs:
            expanded = await expand_container(session, kind, code)
            expanded_containers.append((kind, code, expanded))
            for phone in expanded:
                selected[phone.imei] = phone
        imeis = list(dict.fromkeys([*imeis, *selected]))
    if not imeis:
        raise DomainError("维修单至少需要一台手机")
    if len(set(imeis)) != len(imeis):
        raise DomainError("维修列表包含重复 IMEI")

    return_order = None
    # A return is physically received at the Ghana management office first.
    # ``RepairOrder.location_id`` is the repair-area hand-off destination, so
    # a completed return may legitimately have a different destination
    # location.  Keep the old same-location path for existing integrations,
    # while recording the cross-location triage below as an explicit inventory
    # event.  This avoids making the return itself appear to have arrived in
    # the repair workshop before the receiving/triage operator handled it.
    return_receive_location_id: int | None = None
    cross_location_triage = False
    if return_no:
        return_order = await session.scalar(select(ReturnOrder).where(ReturnOrder.return_no == return_no))
        if return_order is None or return_order.status != DocumentStatus.COMPLETED:
            raise DomainError("退回单不存在或尚未完成接收")
        if return_order.destination_organization_id != organization_id:
            raise DomainError("维修组织与退回目的组织不一致")
        return_receive_location_id = return_order.destination_location_id
        existing_repair = await session.scalar(
            select(RepairOrder).where(RepairOrder.return_order_id == return_order.id)
        )
        if existing_repair is not None:
            raise DomainError(f"该退回单已经建立维修单: {existing_repair.repair_no}")
        if return_receive_location_id != location_id:
            target_location = await session.scalar(
                select(Location).where(Location.id == location_id)
            )
            if target_location is None or str(target_location.location_type).lower() not in {
                "repair", "workshop", "service",
            }:
                raise DomainError("跨地点退回分诊的目标必须是启用的维修区")
            # ``containers`` are expanded as source snapshots.  The physical
            # box/tray itself stays at the management office; each phone is
            # detached below before being handed to the repair area.  This
            # permits a batch scan without falsely relocating a reusable
            # return container or its historical relation.
            cross_location_triage = True

    if cross_location_triage and return_receive_location_id is not None:
        # A cross-location scan must identify a real, active container that is
        # physically at the receiving location.  Without this check an empty
        # or stale box code could be attached to a repair order while the
        # operator manually supplied unrelated IMEIs.  The phone-level checks
        # below still ensure every expanded phone belongs to this return.
        for kind, code, expanded in expanded_containers:
            if kind == ContainerKind.PHONE:
                continue
            container_model = None
            if kind == ContainerKind.TRAY:
                container_model = Tray
            elif kind == ContainerKind.BOX:
                container_model = Box
            if container_model is None:
                raise DomainError(f"维修容器类型不支持: {kind}")
            container = await session.scalar(
                select(container_model).where(container_model.code == code)
            )
            if container is None:
                # ``expand_container`` normally raises this first; retain a
                # domain-level guard in case a new container kind is added.
                raise DomainError(f"维修容器不存在: {code}")
            if not container.is_active:
                raise DomainError(f"退回容器已停用: {code}")
            if container.current_location_id != return_receive_location_id:
                raise DomainError(f"退回容器不在接收地点: {code}")
            if kind == ContainerKind.BOX:
                # A box is only a valid source snapshot when every nested
                # tray is still a live tray at the receiving location.  A
                # stale ``current_box_id`` can otherwise make a tray that has
                # already moved to the workshop look as if it arrived in the
                # return box, allowing the same phone to be triaged twice.
                nested_trays = list(await session.scalars(
                    select(Tray).where(Tray.current_box_id == container.id)
                ))
                for nested_tray in nested_trays:
                    if not nested_tray.is_active:
                        raise DomainError(f"退回箱内托盘已停用: {nested_tray.code}")
                    if nested_tray.current_location_id != return_receive_location_id:
                        raise DomainError(f"退回箱内托盘不在接收地点: {nested_tray.code}")
            if not expanded:
                raise DomainError(f"退回容器为空: {code}")

    phones: list[PhoneDevice] = []
    triage_phone_ids: set[int] = set()
    seen_phone_ids: set[int] = set()
    for imei in imeis:
        phone = await session.scalar(select(PhoneDevice).where((PhoneDevice.imei == imei) | (PhoneDevice.imei2 == imei)))
        if phone is None:
            raise DomainError(f"手机不存在: {imei}")
        if phone.id in seen_phone_ids:
            raise DomainError(f"维修列表包含同一台手机的多个 IMEI: {imei}")
        seen_phone_ids.add(phone.id)
        if phone.current_organization_id != organization_id:
            raise DomainError(f"手机不在维修组织: {imei}")
        if phone.current_location_id != location_id:
            if not (
                cross_location_triage
                and return_receive_location_id is not None
                and phone.current_location_id == return_receive_location_id
            ):
                raise DomainError(f"手机不在维修地点: {imei}")
            triage_phone_ids.add(phone.id)
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
    if container_inputs:
        for kind, code in container_inputs:
            session.add(RepairContainer(repair_order_id=order.id, container_kind=str(kind), container_code=code))
    for phone in phones:
        if phone.id in triage_phone_ids:
            # The return receiver has already completed the inbound check at
            # the management office.  Triage now takes the phone out of its
            # return tray (if any) and hands it to the repair area.  The
            # status remains WAITING_REPAIR; only the physical location
            # changes at this step.
            old_location_id = phone.current_location_id
            if phone.current_tray_id is not None:
                await remove_phone_from_tray(session, phone.imei, action="退回分诊拆托")
            phone.current_location_id = location_id
            session.add(InventoryTransaction(
                phone_id=phone.id,
                action="退回分诊送维修",
                from_status=str(phone.status),
                to_status=str(phone.status),
                from_location_id=old_location_id,
                to_location_id=location_id,
                document_type="repair",
                document_id=order.repair_no,
                operator_id=operator_id,
                note="管理处接收后转入维修区",
            ))
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
