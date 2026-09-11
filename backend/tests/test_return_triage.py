"""Regression coverage for the Ghana return-receive -> repair hand-off."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Box,
    InventoryTransaction,
    Location,
    Organization,
    PhoneDevice,
    PhoneTrayRelation,
    RepairContainer,
    RepairItem,
    ReturnItem,
    ReturnOrder,
    Tray,
)
from app.domain.enums import ContainerKind, DocumentStatus, PhoneStatus
from app.domain.repair_service import create_repair_order


async def test_completed_return_can_be_triaged_from_management_to_repair_area():
    """Receiving and repair are different physical locations.

    The return is completed at GH-MGMT, then the consolidated Ghana operator
    creates a repair order at GH-REPAIR.  The service must move the phone,
    close its old tray relation, and leave an auditable hand-off event.
    """

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    imei = "352099002700041"

    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="GH", name="加纳管理处", country="GH"),
                Location(id=10, organization_id=1, code="GH-MGMT", name="管理处接收区", location_type="warehouse"),
                Location(id=20, organization_id=1, code="GH-REPAIR", name="维修区", location_type="repair"),
                Tray(id=30, code="RET-TRAY-001", current_location_id=10),
                PhoneDevice(
                    id=40,
                    imei=imei,
                    status=PhoneStatus.WAITING_REPAIR,
                    current_organization_id=1,
                    current_location_id=10,
                    current_tray_id=30,
                ),
                ReturnOrder(
                    id=50,
                    return_no="RET-001",
                    sales_order_id=999,
                    source_organization_id=1,
                    source_location_id=10,
                    destination_organization_id=1,
                    destination_location_id=10,
                    status=DocumentStatus.COMPLETED,
                    total_count=1,
                    received_count=1,
                ),
                ReturnItem(return_order_id=50, phone_id=40, imei_snapshot=imei),
                PhoneTrayRelation(phone_id=40, tray_id=30, started_at=datetime.now(timezone.utc)),
            ]
        )
        await session.commit()

        order = await create_repair_order(
            session,
            organization_id=1,
            location_id=20,
            operator_id=100,
            # A whole return tray can be used as the source scan.  The service
            # expands it, detaches each phone, and leaves the reusable tray at
            # the management office.
            imeis=[],
            containers=[(ContainerKind.TRAY, "RET-TRAY-001")],
            return_no="RET-001",
        )
        await session.commit()

        phone = await session.get(PhoneDevice, 40)
        assert phone is not None
        assert phone.current_location_id == 20
        assert phone.current_tray_id is None
        assert await session.scalar(select(RepairItem).where(RepairItem.repair_order_id == order.id)) is not None
        source_tray = await session.get(Tray, 30)
        assert source_tray is not None and source_tray.current_location_id == 10
        repair_container = await session.scalar(select(RepairContainer).where(RepairContainer.repair_order_id == order.id))
        assert repair_container is not None and repair_container.container_code == "RET-TRAY-001"
        actions = list(await session.scalars(select(InventoryTransaction.action).order_by(InventoryTransaction.id)))
        assert actions == ["退回分诊拆托", "退回分诊送维修", "创建送修单"]

        # A retry without the original idempotency key must not create a
        # second repair order for the same return.  The API's idempotency key
        # handles network retries; this domain guard handles a fresh key or a
        # manual duplicate submission.
        with pytest.raises(ValueError, match="已经建立维修单"):
            await create_repair_order(
                session,
                organization_id=1,
                location_id=20,
                operator_id=100,
                imeis=[imei],
                return_no="RET-001",
            )

    await engine.dispose()


async def test_cross_location_triage_rejects_wrong_or_empty_source_container():
    """A source scan cannot smuggle a stale/empty container into a return."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="GH", name="加纳管理处", country="GH"),
                Location(id=10, organization_id=1, code="GH-MGMT", name="管理处接收区", location_type="warehouse"),
                Location(id=20, organization_id=1, code="GH-REPAIR", name="维修区", location_type="repair"),
                # The tray is at the repair area, not at the return receiving
                # area.  Its phone is deliberately still at management to
                # isolate the container-location invariant.
                Tray(id=30, code="STALE-TRAY", current_location_id=20),
                PhoneDevice(
                    id=40,
                    imei="352099002700041",
                    status=PhoneStatus.WAITING_REPAIR,
                    current_organization_id=1,
                    current_location_id=10,
                    current_tray_id=30,
                ),
                ReturnOrder(
                    id=50,
                    return_no="RET-STALE",
                    sales_order_id=999,
                    source_organization_id=1,
                    source_location_id=10,
                    destination_organization_id=1,
                    destination_location_id=10,
                    status=DocumentStatus.COMPLETED,
                    total_count=1,
                    received_count=1,
                ),
                ReturnItem(return_order_id=50, phone_id=40, imei_snapshot="352099002700041"),
            ]
        )
        await session.commit()

        with pytest.raises(ValueError, match="不在接收地点"):
            await create_repair_order(
                session,
                organization_id=1,
                location_id=20,
                operator_id=100,
                imeis=[],
                containers=[(ContainerKind.TRAY, "STALE-TRAY")],
                return_no="RET-STALE",
            )

        # An empty source tray is equally invalid when a caller also supplies
        # a manual IMEI: the container field must describe the physical batch
        # that was opened, not unrelated metadata.
        empty_tray = Tray(id=31, code="EMPTY-TRAY", current_location_id=10)
        session.add(empty_tray)
        await session.commit()
        with pytest.raises(ValueError, match="容器为空"):
            await create_repair_order(
                session,
                organization_id=1,
                location_id=20,
                operator_id=100,
                imeis=["352099002700041"],
                containers=[(ContainerKind.TRAY, "EMPTY-TRAY")],
                return_no="RET-STALE",
            )

        # A box can retain a stale nested-tray pointer after the tray has
        # already been moved to the workshop.  The box itself still appears
        # to be at management, so the repair hand-off must validate the
        # nested tray location rather than trusting the outer box only.
        nested_box = Box(id=32, code="STALE-BOX", current_location_id=10)
        nested_tray = Tray(id=33, code="STALE-NESTED-TRAY", current_location_id=20, current_box_id=32)
        nested_imei = "352099002700058"
        nested_phone = PhoneDevice(
            id=41,
            imei=nested_imei,
            status=PhoneStatus.WAITING_REPAIR,
            current_organization_id=1,
            current_location_id=20,
            current_tray_id=33,
        )
        session.add_all(
            [
                nested_box,
                nested_tray,
                nested_phone,
                ReturnItem(return_order_id=50, phone_id=41, imei_snapshot=nested_imei),
            ]
        )
        await session.commit()
        with pytest.raises(ValueError, match="箱内托盘不在接收地点"):
            await create_repair_order(
                session,
                organization_id=1,
                location_id=20,
                operator_id=100,
                imeis=[],
                containers=[(ContainerKind.BOX, "STALE-BOX")],
                return_no="RET-STALE",
            )

    await engine.dispose()
