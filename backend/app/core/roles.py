"""Canonical operating-role metadata.

The database remains the source of truth for the actual permission links and
data scopes.  This module only supplies stable labels/workgroup metadata for
the API and clients, and documents which historical demo role codes were
merged.  Keeping the metadata in one place prevents the PC and mobile clients
from having to infer a job from an arbitrary permission combination.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoleMetadata:
    code: str
    name: str
    work_group: str
    operations: tuple[str, ...]
    legacy_codes: tuple[str, ...] = ()
    description: str = ""

    @property
    def workgroup(self) -> str:
        """Backward-compatible spelling used by older clients."""

        return self.work_group


ROLE_METADATA: dict[str, RoleMetadata] = {
    "super_admin": RoleMetadata(
        code="super_admin",
        name="超级管理员",
        work_group="SYSTEM",
        operations=("system_admin",),
        description="系统初始化、账号权限和审计管理",
    ),
    "demo_sz_operations": RoleMetadata(
        code="demo_sz_operations",
        name="深圳仓综合作业（收购验收/装托/装箱）",
        work_group="SHENZHEN_OPERATIONS",
        operations=("purchase_receipt", "tray_pack", "box_pack"),
        legacy_codes=("demo_sz_buyer", "demo_sz_tray", "demo_sz_packer"),
        description="同一岗位完成深圳收购验收、装入托盘和装箱封装",
    ),
    "demo_sz_dispatch": RoleMetadata(
        code="demo_sz_dispatch",
        name="深圳发运",
        work_group="SHENZHEN_DISPATCH",
        operations=("shipment_dispatch",),
        description="复核装载、登记物流并确认深圳发运交接",
    ),
    "demo_ghana_operations": RoleMetadata(
        code="demo_ghana_operations",
        name="加纳管理处综合作业（到货/拣货/退回/维修质检）",
        work_group="GHANA_OPERATIONS",
        operations=(
            "inbound_receive",
            "warehouse_pick_dispatch",
            "return_triage",
            "repair_intake",
            "repair_qa",
        ),
        description="同一岗位完成加纳到货验收、仓库拣货发运、退回分诊及维修建单/QA",
        legacy_codes=(
            "demo_gh_receiver",
            "demo_gh_warehouse",
            "demo_gh_return",
            "demo_repair_intake",
            "demo_repair_qa",
        ),
    ),
    "demo_store_a_receiver": RoleMetadata(
        code="demo_store_a_receiver",
        name="门店A收货",
        work_group="STORE_A_RECEIVING",
        operations=("store_receive",),
        description="门店A调拨到货、拆箱拆托并逐台清点",
    ),
    "demo_store_a_clerk": RoleMetadata(
        code="demo_store_a_clerk",
        name="门店A销售退回",
        work_group="STORE_A_SALES",
        operations=("sales_create", "return_create", "stocktake_submit"),
        description="门店A销售、退回发起和盘点提交",
    ),
    "demo_store_a_supervisor": RoleMetadata(
        code="demo_store_a_supervisor",
        name="门店A主管",
        work_group="STORE_A_SUPERVISION",
        operations=("transfer_create", "sales_approve", "stocktake_adjust"),
        description="门店A调拨审批、销售复核和盘点差异处理",
    ),
    "demo_store_b_operator": RoleMetadata(
        code="demo_store_b_operator",
        name="门店B串货作业",
        work_group="STORE_B_OPERATIONS",
        operations=("transfer_create", "store_receive", "sales_create", "return_create"),
        description="门店B串货收发、销售、退回和盘点作业",
    ),
    "demo_return_packer": RoleMetadata(
        code="demo_return_packer",
        name="门店退回打包",
        work_group="STORE_RETURN_PACKING",
        operations=("return_pack",),
        description="门店退回手机的专用托盘/箱装载和发运",
    ),
    "demo_repair_tech": RoleMetadata(
        code="demo_repair_tech",
        name="维修技师",
        work_group="REPAIR_TECHNICIAN",
        operations=("repair_receive", "repair_update"),
        description="接收维修任务并填写检测、维修和配件结果",
    ),
    "demo_auditor": RoleMetadata(
        code="demo_auditor",
        name="报表审计盘点",
        work_group="AUDIT",
        operations=("report_view", "audit_view", "stocktake"),
        description="全局只读追溯、审计和盘点差异复核",
    ),
}


LEGACY_ROLE_TO_CANONICAL: dict[str, str] = {
    legacy: metadata.code
    for metadata in ROLE_METADATA.values()
    for legacy in metadata.legacy_codes
}


def get_role_metadata(code: str) -> RoleMetadata | None:
    """Return metadata for a canonical role code or its legacy alias."""

    canonical = LEGACY_ROLE_TO_CANONICAL.get(code, code)
    return ROLE_METADATA.get(canonical)
