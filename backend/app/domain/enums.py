from enum import StrEnum


class PhoneStatus(StrEnum):
    PENDING_RECEIPT = "待入库"
    SHENZHEN_STOCK = "深圳库存"
    IN_TRAY = "已装托盘"
    IN_BOX = "已装箱待发运"
    IN_TRANSIT = "运输中"
    GHANA_PENDING_INSPECTION = "加纳待验收"
    GHANA_STOCK = "加纳管理处库存"
    STORE_STOCK = "门店库存"
    TRANSFERRING = "调拨中"
    SOLD = "已售出"
    SALE_PENDING = "销售待确认"
    RETURN_PENDING_CHECK = "销售退回待检测"
    WAITING_REPAIR = "待送修"
    REPAIRING = "维修中"
    REPAIR_PENDING_ACCEPTANCE = "维修完成待验收"
    AVAILABLE_AGAIN = "可再次销售"
    FROZEN = "冻结待核查"
    LOST_OR_SCRAPPED = "报损/遗失"


class ContainerKind(StrEnum):
    PHONE = "PHONE"
    TRAY = "TRAY"
    BOX = "BOX"


class DocumentStatus(StrEnum):
    DRAFT = "草稿"
    SUBMITTED = "待审核"
    APPROVED = "已审核"
    COMPLETED = "已完成"
    CANCELLED = "已取消"
    IN_TRANSIT = "运输中"
    RECEIVING = "接收中"
    PARTIAL = "部分差异"
    PENDING_CONFIRMATION = "待确认"
    PENDING_ACCEPTANCE = "待验收"
    IN_PROGRESS = "处理中"
