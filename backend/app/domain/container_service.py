from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Box,
    InventoryTransaction,
    PhoneDevice,
    PhoneTrayRelation,
    Tray,
    TrayBoxRelation,
)
from app.domain.enums import ContainerKind


class DomainError(ValueError):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def find_phone_by_imei(session: AsyncSession, imei: str) -> PhoneDevice | None:
    """Resolve either physical IMEI label to one handset record.

    The scanner may read IMEI1 or IMEI2 depending on which side of a handset
    label is exposed.  Keeping the lookup in one helper prevents individual
    receiving/dispatch/return flows from silently reverting to IMEI1-only
    matching.
    """

    value = imei.strip()
    if not value:
        return None
    return await session.scalar(
        select(PhoneDevice).where((PhoneDevice.imei == value) | (PhoneDevice.imei2 == value))
    )


async def get_phone_by_imei(session: AsyncSession, imei: str) -> PhoneDevice:
    phone = await find_phone_by_imei(session, imei)
    if phone is None:
        raise DomainError(f"IMEI 不存在: {imei}")
    return phone


async def add_phone_to_tray(
    session: AsyncSession, imei: str, tray_code: str, *, action: str = "装入托盘"
) -> PhoneDevice:
    phone = await get_phone_by_imei(session, imei)
    tray = await session.scalar(select(Tray).where(Tray.code == tray_code))
    if tray is None:
        raise DomainError(f"托盘不存在: {tray_code}")
    if phone.current_tray_id is not None and phone.current_tray_id != tray.id:
        raise DomainError(f"手机已在其他托盘中: {imei}")
    if phone.current_tray_id == tray.id:
        return phone

    old_tray_id = phone.current_tray_id
    old_status = str(phone.status)
    phone.current_tray_id = tray.id
    session.add(PhoneTrayRelation(phone_id=phone.id, tray_id=tray.id, started_at=now_utc()))
    session.add(
        InventoryTransaction(
            phone_id=phone.id,
            action=action,
            from_status=old_status,
            to_status=old_status,
            from_tray_id=old_tray_id,
            to_tray_id=tray.id,
        )
    )
    return phone


async def remove_phone_from_tray(
    session: AsyncSession, imei: str, *, action: str = "移出托盘"
) -> PhoneDevice:
    phone = await get_phone_by_imei(session, imei)
    if phone.current_tray_id is None:
        return phone
    old_tray_id = phone.current_tray_id
    relation = await session.scalar(
        select(PhoneTrayRelation).where(
            PhoneTrayRelation.phone_id == phone.id,
            PhoneTrayRelation.tray_id == old_tray_id,
            PhoneTrayRelation.ended_at.is_(None),
        )
    )
    if relation:
        relation.ended_at = now_utc()
    phone.current_tray_id = None
    old_status = str(phone.status)
    session.add(
        InventoryTransaction(
            phone_id=phone.id,
            action=action,
            from_tray_id=old_tray_id,
            to_tray_id=None,
            from_status=old_status,
            to_status=old_status,
        )
    )
    return phone


async def put_tray_in_box(
    session: AsyncSession, tray_code: str, box_code: str, *, action: str = "装入箱子"
) -> Tray:
    tray = await session.scalar(select(Tray).where(Tray.code == tray_code))
    box = await session.scalar(select(Box).where(Box.code == box_code))
    if tray is None:
        raise DomainError(f"托盘不存在: {tray_code}")
    if box is None:
        raise DomainError(f"箱子不存在: {box_code}")
    if tray.current_box_id is not None and tray.current_box_id != box.id:
        raise DomainError(f"托盘已在其他箱子中: {tray_code}")
    if tray.current_box_id == box.id:
        return tray
    old_box_id = tray.current_box_id
    tray.current_box_id = box.id
    session.add(TrayBoxRelation(tray_id=tray.id, box_id=box.id, started_at=now_utc()))
    phone_ids = list(
        await session.scalars(
            select(PhoneDevice.id).where(PhoneDevice.current_tray_id == tray.id)
        )
    )
    for phone_id in phone_ids:
        session.add(
            InventoryTransaction(
                phone_id=phone_id,
                action=action,
                from_box_id=old_box_id,
                to_box_id=box.id,
            )
        )
    return tray


async def remove_tray_from_box(
    session: AsyncSession, tray_code: str, *, action: str = "从箱子取出托盘"
) -> Tray:
    tray = await session.scalar(select(Tray).where(Tray.code == tray_code))
    if tray is None:
        raise DomainError(f"托盘不存在: {tray_code}")
    if tray.current_box_id is None:
        return tray
    relation = await session.scalar(
        select(TrayBoxRelation).where(
            TrayBoxRelation.tray_id == tray.id,
            TrayBoxRelation.box_id == tray.current_box_id,
            TrayBoxRelation.ended_at.is_(None),
        )
    )
    old_box_id = tray.current_box_id
    if relation:
        relation.ended_at = now_utc()
    tray.current_box_id = None
    phone_ids = list(
        await session.scalars(
            select(PhoneDevice.id).where(PhoneDevice.current_tray_id == tray.id)
        )
    )
    for phone_id in phone_ids:
        session.add(
            InventoryTransaction(
                phone_id=phone_id,
                action=action,
                from_box_id=old_box_id,
                to_box_id=None,
            )
        )
    return tray


async def expand_container(
    session: AsyncSession, kind: ContainerKind, code: str
) -> list[PhoneDevice]:
    if kind == ContainerKind.PHONE:
        return [await get_phone_by_imei(session, code)]
    if kind == ContainerKind.TRAY:
        tray = await session.scalar(select(Tray).where(Tray.code == code))
        if tray is None:
            raise DomainError(f"托盘不存在: {code}")
        return list(
            await session.scalars(
                select(PhoneDevice).where(PhoneDevice.current_tray_id == tray.id).order_by(PhoneDevice.id)
            )
        )
    box = await session.scalar(select(Box).where(Box.code == code))
    if box is None:
        raise DomainError(f"箱子不存在: {code}")
    tray_ids = select(Tray.id).where(Tray.current_box_id == box.id)
    return list(
        await session.scalars(
            select(PhoneDevice)
            .where(PhoneDevice.current_tray_id.in_(tray_ids))
            .order_by(PhoneDevice.id)
        )
    )
