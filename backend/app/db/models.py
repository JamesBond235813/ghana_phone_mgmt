from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.domain.enums import DocumentStatus, PhoneStatus


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    country: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Location(TimestampMixin, Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    location_type: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_location_org_code"),)


class PhoneDevice(TimestampMixin, Base):
    __tablename__ = "phone_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    imei: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    imei2: Mapped[str | None] = mapped_column(String(15), unique=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    storage: Mapped[str | None] = mapped_column(String(32))
    color: Mapped[str | None] = mapped_column(String(64))
    condition: Mapped[str | None] = mapped_column(String(32))
    battery_health: Mapped[int | None]
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[PhoneStatus] = mapped_column(String(32), default=PhoneStatus.PENDING_RECEIPT, index=True)
    current_organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    current_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), index=True)
    current_tray_id: Mapped[int | None] = mapped_column(ForeignKey("trays.id"), index=True)


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    supplier: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.COMPLETED)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total_count: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(Text)


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), unique=True, index=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class Shipment(TimestampMixin, Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    origin_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    origin_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    destination_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    destination_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.IN_TRANSIT)
    logistics_no: Mapped[str | None] = mapped_column(String(128))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total_count: Mapped[int] = mapped_column(default=0)


class ShipmentItem(Base):
    __tablename__ = "shipment_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    source_tray_id: Mapped[int | None] = mapped_column(ForeignKey("trays.id"))
    source_box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"))
    __table_args__ = (UniqueConstraint("shipment_id", "phone_id", name="uq_shipment_phone"),)


class ShipmentContainer(Base):
    __tablename__ = "shipment_containers"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    container_kind: Mapped[str] = mapped_column(String(16))
    container_code: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("shipment_id", "container_kind", "container_code", name="uq_shipment_container"),
    )


class ReceivingOrder(TimestampMixin, Base):
    __tablename__ = "receiving_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    receiving_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.RECEIVING)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    expected_count: Mapped[int] = mapped_column(default=0)
    accepted_count: Mapped[int] = mapped_column(default=0)
    exception_count: Mapped[int] = mapped_column(default=0)


class ReceivingItem(Base):
    __tablename__ = "receiving_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receiving_order_id: Mapped[int] = mapped_column(ForeignKey("receiving_orders.id"), index=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    result: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("receiving_order_id", "phone_id", name="uq_receiving_phone"),)


class TransferOrder(TimestampMixin, Base):
    __tablename__ = "transfer_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    destination_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    destination_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.IN_TRANSIT)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total_count: Mapped[int] = mapped_column(default=0)
    received_count: Mapped[int] = mapped_column(default=0)
    exception_count: Mapped[int] = mapped_column(default=0)


class TransferItem(Base):
    __tablename__ = "transfer_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_order_id: Mapped[int] = mapped_column(ForeignKey("transfer_orders.id"), index=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    source_tray_id: Mapped[int | None] = mapped_column(ForeignKey("trays.id"))
    source_box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("transfer_order_id", "phone_id", name="uq_transfer_phone"),)


class TransferContainer(Base):
    __tablename__ = "transfer_containers"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_order_id: Mapped[int] = mapped_column(ForeignKey("transfer_orders.id"), index=True)
    container_kind: Mapped[str] = mapped_column(String(16))
    container_code: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("transfer_order_id", "container_kind", "container_code", name="uq_transfer_container"),
    )


class SalesOrder(TimestampMixin, Base):
    __tablename__ = "sales_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    sales_type: Mapped[str] = mapped_column(String(16))  # RETAIL / WHOLESALE
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.PENDING_CONFIRMATION)
    customer_name: Mapped[str | None] = mapped_column(String(128))
    total_count: Mapped[int] = mapped_column(default=0)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)


class SalesItem(Base):
    __tablename__ = "sales_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), index=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    source_tray_id: Mapped[int | None] = mapped_column(ForeignKey("trays.id"))
    source_box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"))
    __table_args__ = (UniqueConstraint("sales_order_id", "phone_id", name="uq_sales_phone"),)


class SalesContainer(Base):
    __tablename__ = "sales_containers"

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), index=True)
    container_kind: Mapped[str] = mapped_column(String(16))
    container_code: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("sales_order_id", "container_kind", "container_code", name="uq_sales_container"),
    )


class ReturnOrder(TimestampMixin, Base):
    __tablename__ = "return_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), index=True)
    source_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    destination_organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    destination_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.IN_TRANSIT)
    total_count: Mapped[int] = mapped_column(default=0)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    received_count: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(Text)


class ReturnItem(Base):
    __tablename__ = "return_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_order_id: Mapped[int] = mapped_column(ForeignKey("return_orders.id"), index=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("return_order_id", "phone_id", name="uq_return_phone"),)


class ReturnContainer(Base):
    __tablename__ = "return_containers"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_order_id: Mapped[int] = mapped_column(ForeignKey("return_orders.id"), index=True)
    container_kind: Mapped[str] = mapped_column(String(16))
    container_code: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("return_order_id", "container_kind", "container_code", name="uq_return_container"),
    )


class RepairOrder(TimestampMixin, Base):
    __tablename__ = "repair_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    repair_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    return_order_id: Mapped[int | None] = mapped_column(ForeignKey("return_orders.id"), unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.SUBMITTED)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    total_count: Mapped[int] = mapped_column(default=0)
    completed_count: Mapped[int] = mapped_column(default=0)
    accepted_count: Mapped[int] = mapped_column(default=0)
    exception_count: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(Text)


class RepairItem(Base):
    __tablename__ = "repair_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    repair_order_id: Mapped[int] = mapped_column(ForeignKey("repair_orders.id"), index=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    fault_description: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    work_done: Mapped[str | None] = mapped_column(Text)
    parts: Mapped[list | None] = mapped_column(JSON)
    repair_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    repair_result: Mapped[str | None] = mapped_column(String(32))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    disposition: Mapped[str | None] = mapped_column(String(32))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("repair_order_id", "phone_id", name="uq_repair_phone"),)


class RepairContainer(Base):
    __tablename__ = "repair_containers"

    id: Mapped[int] = mapped_column(primary_key=True)
    repair_order_id: Mapped[int] = mapped_column(ForeignKey("repair_orders.id"), index=True)
    container_kind: Mapped[str] = mapped_column(String(16))
    container_code: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("repair_order_id", "container_kind", "container_code", name="uq_repair_container"),
    )


class Tray(TimestampMixin, Base):
    __tablename__ = "trays"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    current_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), index=True)
    current_box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Box(TimestampMixin, Base):
    __tablename__ = "boxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    current_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), index=True)
    seal_code: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PhoneTrayRelation(Base):
    __tablename__ = "phone_tray_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    tray_id: Mapped[int] = mapped_column(ForeignKey("trays.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"))
    __table_args__ = (Index("ix_phone_tray_active", "phone_id", "ended_at"),)


class TrayBoxRelation(Base):
    __tablename__ = "tray_box_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tray_id: Mapped[int] = mapped_column(ForeignKey("trays.id"), index=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"))
    __table_args__ = (Index("ix_tray_box_active", "tray_id", "ended_at"),)


class InventoryTransaction(TimestampMixin, Base):
    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_id: Mapped[int] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    from_tray_id: Mapped[int | None] = mapped_column(ForeignKey("trays.id"))
    to_tray_id: Mapped[int | None] = mapped_column(ForeignKey("trays.id"))
    from_box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"))
    to_box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"))
    document_type: Mapped[str | None] = mapped_column(String(64))
    document_id: Mapped[str | None] = mapped_column(String(64), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    note: Mapped[str | None] = mapped_column(Text)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    # Roles are configuration records that may be retired when an operating
    # model changes.  Keeping the row (rather than deleting it) preserves the
    # meaning of historical audit/user-role records and makes role merges
    # reversible at the data level.  New roles are active by default.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Stable work-group metadata lets clients present a job-oriented workbench
    # without guessing from a changing set of permission codes.
    work_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(128))


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


class UserScope(Base):
    __tablename__ = "user_scopes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    permission_code: Mapped[str] = mapped_column(String(128), index=True)
    scope_kind: Mapped[str] = mapped_column(String(32))
    scope_value: Mapped[str | None] = mapped_column(String(128))
    __table_args__ = (
        UniqueConstraint(
            "user_id", "permission_code", "scope_kind", "scope_value",
            name="uq_user_permission_scope",
        ),
    )


class OperationAudit(Base):
    __tablename__ = "operation_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str] = mapped_column(String(128))
    response: Mapped[dict] = mapped_column(JSON)
    status_code: Mapped[int] = mapped_column(default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StocktakeOrder(TimestampMixin, Base):
    __tablename__ = "stocktake_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    stocktake_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.COMPLETED)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    expected_count: Mapped[int] = mapped_column(default=0)
    found_count: Mapped[int] = mapped_column(default=0)
    missing_count: Mapped[int] = mapped_column(default=0)
    extra_count: Mapped[int] = mapped_column(default=0)
    adjustment_status: Mapped[str] = mapped_column(String(16), default="OPEN")
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class StocktakeItem(Base):
    __tablename__ = "stocktake_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    stocktake_order_id: Mapped[int] = mapped_column(ForeignKey("stocktake_orders.id"), index=True)
    phone_id: Mapped[int | None] = mapped_column(ForeignKey("phone_devices.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    result: Mapped[str] = mapped_column(String(16))
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("stocktake_order_id", "imei_snapshot", name="uq_stocktake_imei"),)


class StocktakeAdjustment(Base):
    __tablename__ = "stocktake_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    stocktake_order_id: Mapped[int] = mapped_column(ForeignKey("stocktake_orders.id"), index=True)
    stocktake_item_id: Mapped[int] = mapped_column(ForeignKey("stocktake_items.id"), index=True)
    imei_snapshot: Mapped[str] = mapped_column(String(15))
    decision: Mapped[str] = mapped_column(String(32))
    target_status: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("stocktake_order_id", "imei_snapshot", name="uq_stocktake_adjustment_imei"),)
