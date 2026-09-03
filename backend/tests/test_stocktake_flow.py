import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Location, Organization, PhoneDevice, StocktakeAdjustment, StocktakeItem
from app.domain.enums import PhoneStatus
from app.domain.stocktake_adjustment_service import adjust_stocktake
from app.domain.stocktake_service import create_stocktake


def test_stocktake_records_found_missing_and_extra():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            org = Organization(id=1, code="GH", name="加纳", country="GH")
            location = Location(id=1, organization_id=1, code="WH", name="管理处", location_type="WAREHOUSE")
            session.add_all([org, location])
            session.add_all([
                PhoneDevice(imei="490154203237518", current_organization_id=1, current_location_id=1, status=PhoneStatus.GHANA_STOCK),
                PhoneDevice(imei="490154203237526", current_organization_id=1, current_location_id=1, status=PhoneStatus.GHANA_STOCK),
            ])
            await session.commit()
            order = await create_stocktake(
                session, organization_id=1, location_id=1, operator_id=9,
                scanned_imeis=["490154203237518", "490154203237534"],
            )
            await session.commit()
            assert (order.expected_count, order.found_count, order.missing_count, order.extra_count) == (2, 1, 1, 1)
            results = list(await session.scalars(select(StocktakeItem.result).order_by(StocktakeItem.id)))
            assert results == ["FOUND", "EXTRA", "MISSING"]
            order = await adjust_stocktake(
                session, stocktake_no=order.stocktake_no, reviewer_id=10,
                adjustments=[{"imei": "490154203237526", "decision": "CONFIRM_MISSING"}],
            )
            assert order.adjustment_status == "OPEN"
            missing_phone = await session.scalar(select(PhoneDevice).where(PhoneDevice.imei == "490154203237526"))
            assert missing_phone.status == PhoneStatus.FROZEN
            order = await adjust_stocktake(
                session, stocktake_no=order.stocktake_no, reviewer_id=10,
                adjustments=[{"imei": "490154203237534", "decision": "IGNORE", "note": "复核后忽略"}],
            )
            assert order.adjustment_status == "COMPLETED"
            assert await session.scalar(select(StocktakeAdjustment.id).where(StocktakeAdjustment.imei_snapshot == "490154203237534")) is not None
        await engine.dispose()
    asyncio.run(run())
