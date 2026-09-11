from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Box, Organization, PhoneDevice, Tray, TrayBoxRelation
from app.domain.container_service import (
    add_phone_to_tray,
    expand_container,
    remove_phone_from_tray,
    remove_tray_from_box,
    put_tray_in_box,
)
from app.domain.enums import ContainerKind, PhoneStatus


async def make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_container_expansion_uses_current_relations_only():
    engine, session_factory = await make_session()
    async with session_factory() as session:
        session.add_all(
            [
                Organization(code="GH", name="加纳管理处", country="GH"),
                PhoneDevice(imei="355240577857876", status=PhoneStatus.GHANA_STOCK),
                PhoneDevice(imei="355240577857877", status=PhoneStatus.GHANA_STOCK),
                Tray(code="TP-001"),
                Tray(code="TP-002"),
                Box(code="BOX-001"),
            ]
        )
        await session.commit()

        await add_phone_to_tray(session, "355240577857876", "TP-001")
        await add_phone_to_tray(session, "355240577857877", "TP-001")
        await put_tray_in_box(session, "TP-001", "BOX-001")
        await session.commit()

        tray_phones = await expand_container(session, ContainerKind.TRAY, "TP-001")
        box_phones = await expand_container(session, ContainerKind.BOX, "BOX-001")
        assert [phone.imei for phone in tray_phones] == ["355240577857876", "355240577857877"]
        assert [phone.imei for phone in box_phones] == ["355240577857876", "355240577857877"]

        await remove_tray_from_box(session, "TP-001")
        await session.commit()
        assert await expand_container(session, ContainerKind.BOX, "BOX-001") == []
        history_count = await session.scalar(select(func.count(TrayBoxRelation.id)))
        assert history_count == 1

    await engine.dispose()


async def test_partial_phone_removal_keeps_remaining_phone_and_container_relations():
    engine, session_factory = await make_session()
    async with session_factory() as session:
        session.add_all(
            [
                Organization(code="GH", name="加纳管理处", country="GH"),
                PhoneDevice(imei="355240577857876", status=PhoneStatus.GHANA_STOCK),
                PhoneDevice(imei="355240577857877", status=PhoneStatus.GHANA_STOCK),
                PhoneDevice(imei="355240577857884", status=PhoneStatus.GHANA_STOCK),
                Tray(code="TP-PARTIAL"),
                Box(code="BOX-PARTIAL"),
            ]
        )
        await session.commit()

        for imei in ("355240577857876", "355240577857877", "355240577857884"):
            await add_phone_to_tray(session, imei, "TP-PARTIAL")
        await put_tray_in_box(session, "TP-PARTIAL", "BOX-PARTIAL")
        await session.commit()

        phone = await session.scalar(select(PhoneDevice).where(PhoneDevice.imei == "355240577857876"))
        assert phone is not None
        await remove_phone_from_tray(session, phone.imei, action="部分出库取出手机")
        await session.commit()

        remaining_tray = await expand_container(session, ContainerKind.TRAY, "TP-PARTIAL")
        remaining_box = await expand_container(session, ContainerKind.BOX, "BOX-PARTIAL")
        assert {item.imei for item in remaining_tray} == {"355240577857877", "355240577857884"}
        assert {item.imei for item in remaining_box} == {"355240577857877", "355240577857884"}

    await engine.dispose()


async def test_phone_container_expansion_accepts_imei2_alias():
    engine, session_factory = await make_session()
    async with session_factory() as session:
        primary = "355240577857876"
        secondary = "355240577857884"
        phone = PhoneDevice(
            imei=primary,
            imei2=secondary,
            status=PhoneStatus.GHANA_STOCK,
        )
        session.add(phone)
        await session.commit()

        expanded = await expand_container(session, ContainerKind.PHONE, secondary)
        assert len(expanded) == 1
        assert expanded[0].id == phone.id

    await engine.dispose()
