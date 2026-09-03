# Ghana Phone Management 产品开发说明书

> 文档版本：1.0（2026-09）  
> 适用范围：运营、仓储、采购、发运、门店、维修、财务/审计、前端、后端、测试与运维人员  
> 项目目录：`/Volumes/little_server/ghanaPhone_management`

## 1. 文档目的与阅读方式

本说明书是本项目的产品、业务和技术交接基线。运营人员可以据此理解从采购到销售、退回和维修的完整链路；开发人员可以据此定位前端页面、后端接口、数据表、权限和状态规则；运维人员可以据此启动服务、执行迁移、初始化管理员并排查常见问题。

本文区分“当前已实现”和“后续建议”。当前代码行为以 `backend/app`、`frontend/src`、`frontend-pc/src` 为准，业务模型的长期约束以 [SYSTEM_DESIGN.md](./SYSTEM_DESIGN.md) 为准。

## 2. 产品定位与范围

系统用于管理深圳到加纳的二手手机跨国流转，以及到货后的仓储、门店、销售、退回、维修和盘点。核心设计是：

```text
IMEI（资产主体） ← 业务单据（操作入口） → 托盘/箱子（可重组容器）
                                  ↓
                         库存流水 + 审计时间线
```

系统不以箱数或托盘数作为库存真相；每次容器级操作都必须展开到具体 IMEI。容器可以拆开、复用和重新组合，历史关系不能被覆盖。

当前产品包含：

- 手机端响应式 Web/PWA：现场扫码、拍照、弱网草稿和轻量任务操作；
- PC 端 Vue/Vite 工作台：左侧权限导航、右侧业务区域，适配 USB 扫码枪；
- FastAPI 后端：认证、RBAC、组织地点、业务单据、库存流水、幂等和审计；
- MySQL 8.x 数据库与 Alembic 迁移；
- 自动化测试：采购、容器、发运、接收、调拨、销售、维修、盘点、安全和管理员查询。

当前不属于已完成范围的项目：真实短信运营商接入、持久化 Refresh Token、生产级文件对象存储、复杂离线冲突审批、完整统计报表、扫码枪网络转发服务和正式生产部署验证。

## 3. 角色与职责

| 角色 | 日常工作 | 允许的核心操作 | 不应承担的操作 |
|---|---|---|---|
| 超级管理员 | 系统初始化、账号和权限 | 管理用户、角色、组织、地点、审计 | 直接改库存；库存纠正必须走业务单据 |
| 运营管理员 | 跨组织业务监督 | 查看全链路、处理异常、查看报表 | 绕过审核删除流水 |
| 采购员 | 深圳采购收货 | 创建采购入库、补录手机资料 | 修改已确认单据、确认加纳收货 |
| 仓库员 | 托盘、箱子和库内整理 | 装托盘、装箱、拆分、盘点、库内移位 | 修改采购价、销售结果 |
| 发运员 | 出口发运 | 创建/确认发运单、物流资料 | 伪造收货结果 |
| 接收验收员 | 加纳到货处理 | 到货、拆箱、逐台验收、登记差异 | 将异常手机直接设为可售 |
| 门店主管 | 门店库存和销售管理 | 收货确认、销售审核、退回、盘点审核 | 查看未授权门店库存 |
| 门店店员 | 现场销售 | 扫码销售、发起退回、执行收货 | 删除销售、批准自己的异常 |
| 维修人员 | 检测与维修 | 接修、记录维修结果、提交复核 | 改写采购或销售单 |
| 财务/报表人员 | 经营核算 | 查看数量、金额和业务报表 | 执行库存操作 |
| 审计人员 | 追责与合规 | 查看 IMEI 时间线、审计和差异 | 新增、修改或删除业务 |
| 运维人员 | 服务运行维护 | 启停服务、迁移、日志和备份 | 使用业务账号代替运营操作 |

权限由“功能权限 + 数据范围 + 单据状态”三层共同决定，前端隐藏入口不等于安全边界；所有后端接口必须再次校验权限和组织/地点范围。

## 4. 业务对象与状态

### 4.1 手机（IMEI）

`PhoneDevice` 以 IMEI 为主键业务标识，支持 `imei2`（双卡第二 IMEI）并建立唯一约束。档案字段包括品牌、型号、容量、颜色、成色、电池健康、采购价、当前状态、当前组织、当前地点、当前托盘和相关业务资料。IMEI 输入必须是 15 位数字并通过 Luhn 校验；双卡设备的两个号码都不能重复。

### 4.2 托盘与箱子

托盘和箱子都有业务编号，但没有固定槽位和容量。托盘承载手机，箱子承载托盘；两者可以为空、拆开或重新组合。当前关系由未结束的关系记录或手机/托盘的当前字段表示，历史关系通过开始/结束时间和触发单据保留。

### 4.3 组织与地点

组织表示公司、国家、管理处或门店；地点表示仓库、门店、接收区、维修区等可操作位置。所有库存变化必须带来源和目标地点；用户只能操作自己数据范围内的组织和地点。

### 4.4 手机状态主链路

```text
待入库 → 深圳库存 → 运输中 → 加纳待验收 → 加纳管理处库存
                                           ↓
                                      门店库存
                                           ↓
                                    销售待确认 → 已售出
                                           ↓
                                销售退回待检测 → 维修中
                                           ↓
                         可再次销售 / 冻结待核查 / 报损
```

实际枚举值以 `backend/app/domain/enums.py` 为准。任何状态改变都必须由领域服务和业务单据触发，禁止提供任意修改库存状态的接口。

## 5. 业务流程与操作要点

### 5.1 采购入库

采购员选择组织和地点，创建采购批次，连续扫描 IMEI。服务端检查格式、校验位、重复性、供应商和当前状态，成功后写入手机档案、采购单明细和库存流水。扫描框支持扫码枪自动回车，也支持手工输入；手工输入必须看到明确校验结果再提交。

### 5.2 装托盘与装箱

先创建/扫描托盘码，再加入一个或多个 IMEI；再创建/扫描箱码并加入托盘码。系统自动展开并显示手机数量。手机已经属于其他托盘时必须提示并拒绝重复加入；拆分或转移要走明确操作，不能覆盖历史关系。

### 5.3 深圳发运

创建发运单，按箱、托盘或散件手机加入货物，填写物流单号、起运地和目的地。确认发运后，明细快照固化，涉及的手机统一进入运输中。后续箱内重组不能改变已经发运的历史快照。

### 5.4 加纳接收和验收

接收员先登记发运到货，再拆箱，逐台扫描验收。每台手机记录正常、缺失、多收、IMEI 不符、运输损坏或待复核。验收通过后才能进入管理处库存；异常进入冻结/差异处理，禁止直接配送门店。

### 5.5 管理处出库、门店收货和调拨

管理处可以按手机、托盘或箱子创建出库。容器级选择只是一种录入入口，服务端始终展开为 IMEI 快照。发出后状态为调拨中，门店逐台或按容器确认收货；短收、多收、错货和损坏生成差异。门店之间调拨复用同样的“发出—接收”双阶段模型。

### 5.6 销售与退回

支持零售和批发，销售可按单台、多台、托盘或箱子操作，保存客户、价格、门店、销售人和付款信息。销售确认前可处于待确认状态；确认后手机进入已售出。退回必须按实际 IMEI 建立明细，先进入销售退回待检测，再由维修/验收流程决定可再次销售、冻结或报损。

### 5.7 维修

退回手机或库存异常手机创建维修单，经历送修、接收、维修完成和复核。维修结论包括已修复、无需维修和不可维修；复核处置包括恢复可售、冻结待核查和报损。每个结论都要记录操作人、时间、备注和库存流水。

### 5.8 盘点

盘点员按地点扫描 IMEI、托盘或箱子。系统比较账面与实扫，形成正常、缺失、多出、位置错误和状态异常。拥有 `stocktake:adjust` 权限的主管处理差异并生成调整流水，盘点人员不能直接改库存。

## 6. 前端产品说明

### 6.1 移动端

目录为 `frontend/`，使用 Vue 3、Vite、TypeScript、PWA 插件和 ZXing。面向仓库、接收、门店等现场人员，提供响应式布局、摄像头扫码、震动/声音反馈、手工录入和离线草稿。摄像头需要 HTTPS 和浏览器授权；不可用时必须保留手工输入入口。

### 6.2 PC 端

目录为 `frontend-pc/`，使用 Vue 3.5、Vite 和 TypeScript。左侧显示当前账号可访问的业务标签，右侧显示工作区；已覆盖工作台、采购、托盘、箱子、发运、接收、调拨、销售、退回、维修、盘点、库存查询、单据、草稿、个人设置和系统管理。

扫码枪以 USB HID Keyboard（键盘模式）接入，扫描结果通过普通输入框的 `v-model` 接收。IMEI 模式收到完整 15 位数字会自动加入，兼容扫码枪不发送回车的配置；提交后会自动恢复焦点。浏览器所在电脑必须就是扫码枪连接的电脑，USB 键盘事件不会跨局域网传到另一台设备。

### 6.3 前端 API 与环境

`frontend-pc/src/api.ts` 和 `frontend/src/api.ts` 统一调用 `/api/v1`；开发环境由 Vite 代理到 `http://127.0.0.1:8000`。PC 开发服务监听 `0.0.0.0:5174`，移动端默认监听 `0.0.0.0:5173`。通过局域网访问时使用 `http://主机IP:5174/`，不是 HTTPS（除非额外配置证书）。

## 7. 后端技术与接口目录

### 7.1 技术栈

- Python 3.x（当前开发环境为 Python 3.13）；
- FastAPI + Uvicorn；
- SQLAlchemy Async ORM + `aiomysql`；
- Pydantic v2；
- MySQL 8.x；
- Alembic 数据库迁移；
- JWT Access Token；密码使用带随机盐的 scrypt 哈希；
- pytest、httpx 作为测试工具。

### 7.2 路由概览

所有业务路由前缀为 `/api/v1`：

| 模块 | 主要接口 |
|---|---|
| 认证 | `POST /auth/password`、`GET /auth/me`、`PATCH /auth/profile`、`PATCH /auth/password`、`GET /auth/work-locations`、短信占位接口 |
| 库存 | `POST /inventory/purchase-receipts`、`POST /inventory/trays`、`POST /inventory/boxes`、`GET /inventory/phones/{imei}`、`GET /inventory/phones` |
| 发运/接收 | `POST /shipments/dispatch`、`POST /shipments/receiving/start`、`POST /shipments/receiving/inspect` |
| 调拨 | `POST /transfers/issue`、`POST /transfers/receive` |
| 销售/退回 | `POST /sales`、`POST /sales/{sales_no}/confirm`、`POST /sales/{sales_no}/cancel`、`POST /returns`、`POST /returns/receive` |
| 维修 | `POST /repairs`、`POST /repairs/{repair_no}/accept`、`POST /repairs/{repair_no}/complete`、`POST /repairs/{repair_no}/review` |
| 盘点 | `POST /stocktakes`、`POST /stocktakes/{stocktake_no}/adjust` |
| 查询 | `GET /documents`、`GET /inventory/phones`、`GET /inventory/phones/{imei}` |
| 管理 | 组织、地点、权限、角色、用户的 GET/POST/PATCH，以及 `GET /admin/audits` |
| 系统 | `GET /health` |

改变库存的 POST 接口应带 `X-Idempotency-Key`。同一用户、同一操作、同一键重复提交时返回第一次结果，避免网络重试产生重复业务。

## 8. 数据模型与完整性规则

核心 SQLAlchemy 模型位于 `backend/app/db/models.py`：

```text
Organization / Location
PhoneDevice
Tray / Box / PhoneTrayRelation / TrayBoxRelation
PurchaseOrder / PurchaseItem
Shipment / ShipmentItem / ShipmentContainer
ReceivingOrder / ReceivingItem
TransferOrder / TransferItem / TransferContainer
SalesOrder / SalesItem / SalesContainer
ReturnOrder / ReturnItem / ReturnContainer
RepairOrder / RepairItem / RepairContainer
StocktakeOrder / StocktakeItem / StocktakeAdjustment
InventoryTransaction
User / Role / Permission / UserRole / RolePermission / UserScope
OperationAudit / IdempotencyRecord
```

必须遵守：

1. IMEI、IMEI2 唯一；输入先做格式和 Luhn 校验。
2. 库存变化在一个数据库事务内完成：校验、单据、明细、当前状态、流水、审计和幂等记录要么全部成功，要么全部回滚。
3. 容器级单据固化提交时的 IMEI 明细快照；不能事后按当前箱内内容重算历史。
4. 历史关系和库存流水不可物理删除；撤销和更正必须生成新记录并说明原因。
5. 所有查询都先按权限和数据范围过滤，再返回业务数据；金额字段需要额外报表权限。

## 9. 部署、启动和配置

### 9.1 后端开发启动

```bash
cd /Volumes/little_server/ghanaPhone_management
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 9.2 前端开发启动

```bash
cd /Volumes/little_server/ghanaPhone_management/frontend-pc
npm install
npm run dev -- --host 0.0.0.0 --port 5174

cd /Volumes/little_server/ghanaPhone_management/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 9.3 数据库迁移和管理员

在 `backend/.env` 或环境变量中配置 `DATABASE_URL`，格式为 `mysql+aiomysql://用户:密码@主机:3306/数据库`。执行：

```bash
cd /Volumes/little_server/ghanaPhone_management/backend
../.venv/bin/alembic upgrade head
PYTHONPATH=. ../.venv/bin/python scripts/bootstrap_super_admin.py \
  --database-url "$DATABASE_URL" --username <管理员用户名>
```

当前 Alembic head 为 `0008_usernames`。生产环境只执行显式 migration，不执行未经评审的 `downgrade`，不把真实数据库密码提交到代码、日志或截图。

### 9.4 运行检查

- 后端：`curl http://127.0.0.1:8000/health` 应返回 `{"status":"ok"...}`；
- PC：浏览器打开 `http://主机IP:5174/`；
- 移动端：浏览器打开 `http://主机IP:5173/`；
- 局域网访问要求主机防火墙允许 5173、5174、8000，且服务监听 `0.0.0.0`；
- 浏览器跨域问题检查 `backend/.env` 中的 `CORS_ORIGINS` 和 `CORS_ORIGIN_REGEX`。

## 10. 测试与验收

后端测试位于 `backend/tests/`，建议每次变更执行：

```bash
cd /Volumes/little_server/ghanaPhone_management/backend
../.venv/bin/pytest -q
```

验收至少覆盖：登录和无权限拒绝、IMEI 重复与非法校验、采购入库、托盘/箱子重组、发运、接收差异、调拨收货、零售/批发销售、退回维修、盘点调整、重复幂等请求、数据范围隔离和审计记录。

扫码枪验收分三层：

1. 在 TextEdit 扫描，确认能输出完整字符；
2. 在 PC 输入框扫描，确认即时显示并自动加入；
3. 提交采购或盘点单，确认服务端收到 IMEI 并生成流水。

如果 TextEdit 无输出，先排查 USB 数据线、USB-C 转接头和 HID 键盘模式；如果 TextEdit 有输出但 PC 无输出，检查页面焦点、强制刷新和浏览器控制台。扫码枪连接在一台电脑时，不能期待另一台局域网电脑的浏览器直接接收其键盘事件。

## 11. 故障排查手册

### 登录失败

检查后端是否健康、数据库是否可连接、账号是否启用；用户名登录使用 `identifier`，手机号登录可使用 `phone`。确认浏览器访问的是当前 PC 端口 5174，而不是移动端 5173。

### 页面能打开但接口失败

检查浏览器开发者工具 Network；确认请求前缀为 `/api/v1`，后端在 8000 端口，CORS 允许当前来源。局域网客户端不能把后端地址写成客户端自己的 `127.0.0.1`。

### 扫码无反应

先在本机 TextEdit 验证 HID 输入，再确认网页输入框有焦点。扫描后没有回车时，PC 端 IMEI 输入框会在满 15 位时自动加入；非 IMEI 容器码仍需要回车或点击“加入”。检查扫码枪是否配置成 USB HID Keyboard，而不是 USB COM/Serial。

### 数据重复提交

确认前端每次业务操作生成并复用 `X-Idempotency-Key`；服务端检查 `IdempotencyRecord`。不要通过刷新页面或重复点击绕过业务状态检查。

### 盘点差异无法关闭

必须由具备 `stocktake:adjust` 的主管逐条处理差异，指定合法目标状态或选择忽略；调整会生成新的流水，不能直接编辑原盘点结果。

## 12. 运维、备份和安全要求

- MySQL 按日全量备份、按小时增量/binlog，至少保留一份异地副本；定期做恢复演练。
- 生产环境关闭 `--reload`，使用进程管理器或容器运行 Uvicorn，并配置反向代理、HTTPS、限流和访问日志。
- JWT secret、数据库密码、短信密钥和对象存储密钥只放在环境变量或密钥管理系统。
- 审计日志、库存流水和幂等记录默认长期保留；业务撤销不删除原记录。
- 生产数据库账号遵守最小权限，应用账号不授予结构变更权限。
- 监控健康检查、响应时间、5xx、数据库连接池、磁盘、备份成功率和待同步草稿数量。
- 附件上传需限制类型和大小，病毒扫描后存入对象存储；数据库只保存元数据和不可变引用。

## 13. 后续优化路线

### P0：上线前必须完成

1. 接入真实短信供应商和验证码限流；
2. 实现 Refresh Token 持久化、撤销和设备会话管理；
3. 完成生产 MySQL、备份恢复、HTTPS、反向代理和监控；
4. 补齐扫码枪兼容矩阵，提供厂商配置条码和可视化诊断页；
5. 对所有金额、差异和异常流程补充审核与权限测试。

### P1：提高现场效率

1. 建立 Mac/Windows 扫码枪桥接服务，支持扫码枪固定连接服务器、浏览器在其他设备使用的场景；
2. 批量导入/导出、打印箱标/托盘标和业务单据；
3. 增加实时库存看板、发运在途和门店缺货提醒；
4. 离线队列增加冲突预览、逐条重试和主管审批；
5. 支持照片压缩、断点上传和附件预览。

### P2：数据和智能化

1. 统一经营报表、毛利、周转天数和异常率；
2. 增加事件总线和异步通知，减少长事务；
3. 引入条码质量分析、重复扫描分析和设备运行统计；
4. 对维修故障、销售和库存损耗做趋势预测；
5. 建立 API 版本管理、契约测试和端到端自动化回归。

## 14. 开发维护约定

新增业务时必须先更新状态机、权限矩阵和数据模型，再实现领域服务和 API，最后补前端入口与测试。不要增加“任意修改状态/地点/容器”的快捷接口；不要通过前端隐藏来代替后端权限；不要覆盖历史关系；不要把真实密码和客户数据写入日志。

提交代码前检查：`pytest -q`、两个前端 `npm run build`、Alembic migration 是否可重复执行、接口是否有数据范围测试、异常是否产生审计、重试是否幂等、移动端和 PC 端业务语义是否保持一致。

