"""The warehouse scanner may read either IMEI label on a dual-SIM phone."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Location,
    Organization,
    PhoneDevice,
    ReturnItem,
    SalesItem,
    SalesOrder,
    TransferItem,
    TransferOrder,
)
from app.domain.enums import DocumentStatus, PhoneStatus
from app.domain.sales_service import create_return, receive_return
from app.domain.transfer_service import receive_transfer


async def test_transfer_and_return_receive_accept_imei2_alias():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    imei1 = "352099002700017"
    imei2 = "352099002700025"

    async with factory() as session:
        session.add_all(
            [
                Organization(id=1, code="GH", name="加纳", country="GH"),
                Organization(id=2, code="STORE", name="门店", country="GH"),
                Location(id=10, organization_id=1, code="GH-MGMT", name="管理处", location_type="warehouse"),
                Location(id=20, organization_id=2, code="STORE-A", name="门店A", location_type="store"),
                PhoneDevice(
                    id=100,
                    imei=imei1,
                    imei2=imei2,
                    status=PhoneStatus.TRANSFERRING,
                    current_organization_id=None,
                    current_location_id=None,
                ),
                TransferOrder(
                    id=200,
                    transfer_no="TRF-ALIAS",
                    source_organization_id=1,
                    source_location_id=10,
                    destination_organization_id=2,
                    destination_location_id=20,
                    status=DocumentStatus.IN_TRANSIT,
                    total_count=1,
                ),
                TransferItem(transfer_order_id=200, phone_id=100, imei_snapshot=imei1),
            ]
        )
        await session.commit()

        transfer = await receive_transfer(
            session,
            transfer_no="TRF-ALIAS",
            received_imeis=[imei2],
            operator_id=900,
            complete=True,
        )
        assert transfer.status == DocumentStatus.COMPLETED
        phone = await session.get(PhoneDevice, 100)
        assert phone is not None
        assert phone.status == PhoneStatus.STORE_STOCK
        assert phone.current_location_id == 20

        # Reuse the same phone in a completed sale and verify that both return
        # creation and management-office receipt resolve IMEI2 to phone_id.
        phone.status = PhoneStatus.SOLD
        phone.current_organization_id = None
        phone.current_location_id = None
        sale = SalesOrder(
            id=300,
            sales_no="SALE-ALIAS",
            organization_id=2,
            location_id=20,
            sales_type="RETAIL",
            status=DocumentStatus.COMPLETED,
            total_count=1,
        )
        session.add_all([sale, SalesItem(sales_order_id=300, phone_id=100, imei_snapshot=imei1)])
        await session.commit()

        returned = await create_return(
            session,
            sales_no="SALE-ALIAS",
            source_organization_id=2,
            source_location_id=20,
            destination_organization_id=1,
            destination_location_id=10,
            operator_id=901,
            imeis=[imei2],
        )
        item = await session.scalar(
            select(ReturnItem).where(ReturnItem.return_order_id == returned.id)
        )
        assert item is not None and item.phone_id == 100 and item.imei_snapshot == imei1

        received = await receive_return(
            session,
            return_no=returned.return_no,
            received_imeis=[imei2],
            operator_id=902,
        )
        assert received.status == DocumentStatus.COMPLETED
        phone = await session.get(PhoneDevice, 100)
        assert phone is not None
        assert phone.status == PhoneStatus.WAITING_REPAIR
        assert phone.current_location_id == 10

    await engine.dispose()
