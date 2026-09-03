"""Create a small, repeatable demo dataset for the inventory and documents pages."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import (
    Box, InventoryTransaction, Location, Organization, PhoneDevice, PurchaseItem,
    PurchaseOrder, ReceivingItem, ReceivingOrder, RepairItem, RepairOrder,
    ReturnItem, ReturnOrder, SalesItem, SalesOrder, Shipment, ShipmentContainer,
    ShipmentItem, StocktakeItem, StocktakeOrder, Tray, TrayBoxRelation,
    PhoneTrayRelation, TransferItem, TransferOrder, User,
)
from app.domain.enums import DocumentStatus, PhoneStatus


def demo_imei(index: int) -> str:
    stem = f"3520990017{index:04d}"
    total = 0
    for position, digit in enumerate(reversed(stem)):
        value = int(digit) * (2 if position % 2 == 0 else 1)
        total += value // 10 + value % 10
    return stem + str((10 - total % 10) % 10)


async def seed(database_url: str = settings.database_url) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        marker = await session.scalar(select(PhoneDevice).where(PhoneDevice.imei == demo_imei(1)))
        if marker is not None:
            print("演示数据已存在，未重复创建。")
            await session.close()
            await engine.dispose()
            return

        operator = await session.scalar(select(User).order_by(User.id))
        operator_id = operator.id if operator else None

        sz = Organization(code="DEMO-SZ", name="演示深圳组织", country="CN")
        gh = Organization(code="DEMO-GH", name="演示加纳组织", country="GH")
        session.add_all([sz, gh])
        await session.flush()
        sz_wh = Location(organization_id=sz.id, code="DEMO-SZ-WH", name="深圳演示仓", location_type="warehouse")
        gh_mgmt = Location(organization_id=gh.id, code="DEMO-GH-MGMT", name="加纳管理处演示仓", location_type="warehouse")
        gh_store = Location(organization_id=gh.id, code="DEMO-GH-STORE-01", name="加纳演示门店 01", location_type="store")
        gh_repair = Location(organization_id=gh.id, code="DEMO-GH-REPAIR", name="加纳演示维修区", location_type="repair")
        session.add_all([sz_wh, gh_mgmt, gh_store, gh_repair])
        await session.flush()

        trays = [
            Tray(code="DEMO-TRAY-SZ-01", current_location_id=sz_wh.id),
            Tray(code="DEMO-TRAY-SZ-02", current_location_id=sz_wh.id),
            Tray(code="DEMO-TRAY-GH-01", current_location_id=gh_mgmt.id),
        ]
        boxes = [
            Box(code="DEMO-BOX-SZ-01", current_location_id=sz_wh.id),
            Box(code="DEMO-BOX-GH-01", current_location_id=gh_mgmt.id),
        ]
        session.add_all([*trays, *boxes])
        await session.flush()
        trays[1].current_box_id = boxes[0].id
        trays[2].current_box_id = boxes[1].id
        now = datetime.now(timezone.utc)
        session.add_all([
            TrayBoxRelation(tray_id=trays[1].id, box_id=boxes[0].id, started_at=now),
            TrayBoxRelation(tray_id=trays[2].id, box_id=boxes[1].id, started_at=now),
        ])

        stages = [
            (PhoneStatus.SHENZHEN_STOCK, sz.id, sz_wh.id, None),
            (PhoneStatus.IN_TRAY, sz.id, sz_wh.id, trays[0].id),
            (PhoneStatus.IN_BOX, sz.id, sz_wh.id, trays[1].id),
            (PhoneStatus.IN_TRANSIT, None, None, None),
            (PhoneStatus.GHANA_PENDING_INSPECTION, gh.id, gh_mgmt.id, None),
            (PhoneStatus.GHANA_STOCK, gh.id, gh_mgmt.id, trays[2].id),
            (PhoneStatus.STORE_STOCK, gh.id, gh_store.id, None),
            (PhoneStatus.SALE_PENDING, gh.id, gh_store.id, None),
            (PhoneStatus.SOLD, None, None, None),
            (PhoneStatus.RETURN_PENDING_CHECK, None, None, None),
            (PhoneStatus.WAITING_REPAIR, gh.id, gh_repair.id, None),
            (PhoneStatus.REPAIRING, gh.id, gh_repair.id, None),
            (PhoneStatus.REPAIR_PENDING_ACCEPTANCE, gh.id, gh_repair.id, None),
            (PhoneStatus.AVAILABLE_AGAIN, gh.id, gh_mgmt.id, None),
        ]
        phones: list[PhoneDevice] = []
        for index, (status, org_id, location_id, tray_id) in enumerate(stages, 1):
            phone = PhoneDevice(
                imei=demo_imei(index), brand="Apple" if index % 2 else "Samsung",
                model="iPhone 13" if index % 2 else "Galaxy S22", storage="128GB",
                color="黑色", condition="良好", battery_health=88 + index % 10,
                purchase_price=Decimal("180.00") + index, status=status,
                current_organization_id=org_id, current_location_id=location_id,
                current_tray_id=tray_id,
            )
            phones.append(phone)
            session.add(phone)
        await session.flush()
        for index, phone in enumerate(phones, 1):
            if stages[index - 1][3]:
                session.add(PhoneTrayRelation(phone_id=phone.id, tray_id=stages[index - 1][3], started_at=now))

        purchase = PurchaseOrder(order_no="DEMO-PO-001", organization_id=sz.id, supplier="演示供应商", status=DocumentStatus.COMPLETED, operator_id=operator_id, total_count=len(phones), note="演示：深圳采购入库")
        session.add(purchase)
        await session.flush()
        session.add_all([PurchaseItem(purchase_order_id=purchase.id, phone_id=phone.id, purchase_price=phone.purchase_price) for phone in phones])

        shipment = Shipment(shipment_no="DEMO-SHIP-001", origin_organization_id=sz.id, origin_location_id=sz_wh.id, destination_organization_id=gh.id, destination_location_id=gh_mgmt.id, status=DocumentStatus.IN_TRANSIT, logistics_no="DEMO-LOGISTICS-001", operator_id=operator_id, total_count=1)
        session.add(shipment)
        await session.flush()
        session.add_all([ShipmentContainer(shipment_id=shipment.id, container_kind="BOX", container_code="DEMO-BOX-SZ-01"), ShipmentItem(shipment_id=shipment.id, phone_id=phones[3].id, imei_snapshot=phones[3].imei)])

        receiving = ReceivingOrder(receiving_no="DEMO-RCV-001", shipment_id=shipment.id, organization_id=gh.id, location_id=gh_mgmt.id, status=DocumentStatus.RECEIVING, operator_id=operator_id, expected_count=1, accepted_count=0, exception_count=0)
        session.add(receiving)
        await session.flush()
        session.add(ReceivingItem(receiving_order_id=receiving.id, phone_id=phones[4].id, imei_snapshot=phones[4].imei, result=None))

        transfer = TransferOrder(transfer_no="DEMO-TRF-001", source_organization_id=gh.id, source_location_id=gh_mgmt.id, destination_organization_id=gh.id, destination_location_id=gh_store.id, status=DocumentStatus.COMPLETED, operator_id=operator_id, total_count=1, received_count=1)
        session.add(transfer)
        await session.flush()
        session.add(TransferItem(transfer_order_id=transfer.id, phone_id=phones[6].id, imei_snapshot=phones[6].imei, received_at=now))

        sale_pending = SalesOrder(sales_no="DEMO-SALE-001", organization_id=gh.id, location_id=gh_store.id, sales_type="RETAIL", status=DocumentStatus.PENDING_CONFIRMATION, customer_name="演示客户 A", total_count=1, total_amount=Decimal("299.00"), operator_id=operator_id)
        sale_done = SalesOrder(sales_no="DEMO-SALE-002", organization_id=gh.id, location_id=gh_store.id, sales_type="WHOLESALE", status=DocumentStatus.COMPLETED, customer_name="演示批发客户", total_count=1, total_amount=Decimal("280.00"), operator_id=operator_id)
        session.add_all([sale_pending, sale_done])
        await session.flush()
        session.add_all([SalesItem(sales_order_id=sale_pending.id, phone_id=phones[7].id, imei_snapshot=phones[7].imei, sale_price=Decimal("299.00")), SalesItem(sales_order_id=sale_done.id, phone_id=phones[8].id, imei_snapshot=phones[8].imei, sale_price=Decimal("280.00"))])

        return_order = ReturnOrder(return_no="DEMO-RET-001", sales_order_id=sale_done.id, source_organization_id=gh.id, source_location_id=gh_store.id, destination_organization_id=gh.id, destination_location_id=gh_mgmt.id, status=DocumentStatus.IN_TRANSIT, total_count=1, operator_id=operator_id)
        session.add(return_order)
        await session.flush()
        session.add(ReturnItem(return_order_id=return_order.id, phone_id=phones[9].id, imei_snapshot=phones[9].imei))

        repair_active = RepairOrder(repair_no="DEMO-REP-001", organization_id=gh.id, location_id=gh_repair.id, status=DocumentStatus.IN_PROGRESS, operator_id=operator_id, technician_id=operator_id, total_count=1)
        repair_done = RepairOrder(repair_no="DEMO-REP-002", organization_id=gh.id, location_id=gh_repair.id, status=DocumentStatus.PENDING_ACCEPTANCE, operator_id=operator_id, total_count=1, completed_count=1)
        session.add_all([repair_active, repair_done])
        await session.flush()
        session.add_all([RepairItem(repair_order_id=repair_active.id, phone_id=phones[11].id, imei_snapshot=phones[11].imei, fault_description="屏幕触控异常"), RepairItem(repair_order_id=repair_done.id, phone_id=phones[12].id, imei_snapshot=phones[12].imei, repair_result="REPAIRED", completed_at=now, completed_by=operator_id)])

        stocktake = StocktakeOrder(stocktake_no="DEMO-ST-001", organization_id=gh.id, location_id=gh_store.id, status=DocumentStatus.COMPLETED, operator_id=operator_id, expected_count=1, found_count=1, missing_count=0, extra_count=0, adjustment_status="CLOSED", reviewer_id=operator_id, reviewed_at=now, note="演示：门店盘点")
        session.add(stocktake)
        await session.flush()
        session.add(StocktakeItem(stocktake_order_id=stocktake.id, phone_id=phones[6].id, imei_snapshot=phones[6].imei, result="FOUND", scanned_at=now))

        status_by_phone = [
            "采购入库", "装入托盘", "装入箱子", "深圳发运", "加纳到货待验收", "加纳验收重新装入托盘",
            "门店调拨收货", "销售待确认", "销售确认", "销售退回发出", "创建送修单", "维修人员接收",
            "维修完成待验收", "维修结果验收",
        ]
        for phone, (status, org_id, location_id, tray_id), action in zip(phones, stages, status_by_phone):
            session.add(InventoryTransaction(phone_id=phone.id, action=action, from_status=None, to_status=str(status), to_location_id=location_id, to_tray_id=tray_id, operator_id=operator_id, note="演示数据"))
        await session.commit()
        print(f"演示数据创建完成：{len(phones)} 台手机，覆盖库存状态和业务单据。")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
