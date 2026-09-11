# 开源进销存/仓储系统调研与本项目改造建议

## 结论

本项目不适合直接替换成一套完整 ERP。最值得借鉴的是 **ERPNext 的不可变库存流水 + 序列号约束**、**Odoo Inventory 的仓库/库位/包装层级和条码作业**，以及 **InvenTree 的序列化库存 API、移动端和插件化思路**。建议保留现有 FastAPI + Vue 3 技术栈，在当前领域模型上实现“容器作业会话（Container Work Session）”，而不是把手机逐台当成孤立的单据提交。

## 候选项目

### 1. ERPNext

- 仓库：https://github.com/frappe/erpnext
- 序列号实现：https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/serial_no/serial_no.py
- 库存流水设计：https://github.com/frappe/erpnext/blob/develop/erpnext/stock/spec/README.md
- 许可证：仓库标注 GPLv3。
- 可借鉴点：采购入库、库存调拨、销售出库都通过 Stock Ledger Entry 形成可追溯流水；序列号不能绕过库存交易直接改变仓库归属；支持批量解析/导入序列号。
- 不直接采用的部分：Frappe/ERPNext 运行时和全套会计/采购模型远大于本项目，引入成本高，且会破坏当前 FastAPI API 边界。

### 2. Odoo Inventory

- 仓库：https://github.com/odoo/odoo
- 库位/仓库模型：https://github.com/odoo/odoo/blob/19.0/addons/stock/models/stock_warehouse.py
- Lot/Serial 模型：https://github.com/odoo/odoo/blob/19.0/addons/stock/models/stock_lot.py
- 条码与序列号说明：https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/barcode/setup/serial_numbers_lots.html
- 许可证：Odoo 社区核心采用 LGPL-3.0。
- 可借鉴点：仓库下分接收区、质检区、包装区、库存区；条码作业以“扫描作业/库位/包装”推进；Package 是一等容器，Lot/Serial 记录可绑定目标 Package；支持一次粘贴/导入多个序列号。
- 对本项目的直接启发：把“托盘编码”作为一次作业的目标容器，之后每次扫描 IMEI 都是同一作业中的明细追加，提交/关闭作业时统一落库存流水。

### 3. InvenTree

- 仓库：https://github.com/inventree/inventree
- 许可证：MIT。
- 项目特点：Python/Django 后端、REST API、序列化/批次库存、移动端配套应用和插件系统；仓库主页显示项目持续发布并有较大的社区规模。
- 可借鉴点：API 优先、库存对象与批次/序列号对象分层、移动设备作为现场作业入口、插件化集成。
- 不直接采用的部分：Django ORM 与现有 SQLAlchemy/FastAPI 不兼容，适合参考领域边界和移动交互，不适合原样移植代码。

### 4. OCA WMS

- 仓库：https://github.com/OCA/wms
- 许可证：各模块需逐项核对，遵循 OCA 政策。
- 可借鉴点：仓库、库位、Picking、Move、Lot、Package 的扩展模块，以及 `stock-logistics-barcode`、`stock-logistics-tracking` 等现场条码和包装跟踪能力。
- 适用方式：参考模块拆分方式，为本项目拆出容器作业、扫描明细、库存移动和异常处理边界。

### 5. Dolibarr

- 仓库：https://github.com/Dolibarr/dolibarr
- Lot/Serial 开发说明：https://wiki.dolibarr.org/index.php/Module_Lot_/_Serial_%28developer%29
- 许可证：GPL-3.0。
- 可借鉴点：成熟的采购、销售、库存、批次/序列号和多组织基础模块。
- 不直接采用的部分：PHP 生态，与本项目技术栈差异较大；主要用于对照业务完整性和报表覆盖。

### 6. Snipe-IT

- 仓库：https://github.com/grokability/snipe-it
- 许可证：AGPL-3.0。
- 可借鉴点：资产唯一序列号、资产生命周期、责任归属和审计轨迹。
- 不直接采用的部分：它偏 IT 资产领用管理，不是托盘/箱子/仓库作业系统；不适合作为本项目主框架。

## 适合本业务的目标流程

### 托盘装机作业

1. 扫描或手工录入托盘编码。
2. 后端校验托盘存在、地点一致、未封存且仍有空位，创建一个 `container_work_session`，状态为 `OPEN`。
3. 操作员连续扫描手机 IMEI；每次扫描只提交一个轻量追加请求，后端校验 IMEI 唯一、手机在同一地点、未在其他托盘，并写入会话明细和预览计数。
4. 页面持续显示：已录入数量、剩余容量、重复/冲突项、最近扫描记录；重复扫描应幂等返回而不是产生第二条关系。
5. 点击“完成装盘”后，后端在一个事务中关闭会话、写入每台手机的托盘关系和库存流水；若业务需要现场即时可见，也可以在每次追加时落当前关系，但必须保留会话状态以支持撤销和异常复核。
6. 扫描托盘编码即可查看内容；封存后禁止继续追加，只能走“拆盘/移盘”作业。

### 数据模型建议

- 保留 `trays`、`boxes`、`phone_devices` 和历史关系表。
- 新增 `container_work_sessions`：目标容器、地点、作业类型、操作员、状态、容量快照、开始/结束时间。
- 新增 `container_work_items`：会话、IMEI/phone_id、扫描顺序、扫描时间、结果（accepted/duplicate/conflict/rejected）、错误原因。
- `Tray` 增加容量/封存状态（若实际托盘规格固定，也可配置到托盘类型表）。
- 所有确认后的关系变更继续写入 `inventory_transactions`，禁止通过普通更新接口直接改库存。
- 追加接口使用 `X-Idempotency-Key`，并以“会话 + IMEI”建立唯一约束，确保重复扫码安全。

### 前端交互建议

- 手机端默认进入“装入托盘”任务：先聚焦托盘输入框，确认后自动切换到 IMEI 扫描输入框。
- 扫描成功立即清空输入框并显示绿色短反馈，失败项固定显示在异常列表，不打断后续扫描。
- 支持连续扫码、手工输入、批量粘贴三种模式；完成按钮显示数量和容量，不要求操作员重复填写托盘编码。
- PC 端提供会话列表、异常复核、撤销未提交项、封存和打印托盘标签。

## 实施顺序

1. 先实现后端容器作业会话和 IMEI 连续追加 API，并补充唯一约束、权限和审计测试。
2. 再改造手机端装盘页面，保留现有一次性 `imeis` 参数作为兼容接口。
3. 接着把箱子装盘、发运、加纳接收复用同一套会话抽象。
4. 最后补充托盘容量、封存、异常复核、批量导入和操作报表。

