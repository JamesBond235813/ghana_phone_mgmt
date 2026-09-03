# 移动端与 PC 端功能对照

| 业务 | 权限 | 移动端 | PC 端 | 核心接口 |
|---|---|---|---|---|
| 采购入库 | `purchase:create` | 摄像头/手工 IMEI | 扫码枪/手工 IMEI | `/inventory/purchase-receipts` |
| 装托盘 | `tray:manage` | IMEI 扫描 | 扫码枪 IMEI | `/inventory/trays` |
| 装箱 | `box:manage` | 托盘编号 | 扫码枪托盘编号 | `/inventory/boxes` |
| 发运出库 | `shipment:dispatch` | 手机/托盘/箱子 | 手机/托盘/箱子 | `/shipments/dispatch` |
| 接收验收 | `receiving:unpack/accept` | 建单、逐台验收 | 建单、逐台验收 | `/shipments/receiving/*` |
| 门店调拨 | `transfer:create/receive` | 发起、收货 | 发起、收货 | `/transfers/*` |
| 销售 | `sales:create/approve` | 制单、确认 | 制单、确认 | `/sales/*` |
| 销售退回 | `return:create/receive` | 发起、接收 | 发起、接收 | `/returns/*` |
| 维修 | `repair:create/receive/update/approve` | 建单、接收、结果、复核 | 建单、接收、结果、复核 | `/repairs/*` |
| 盘点 | `stocktake:submit/adjust` | 提交、差异审核 | 提交、差异审核 | `/stocktakes/*` |
| 手机查询 | `phone:view` | IMEI 轨迹 | IMEI 详情 | `/inventory/phones/*` |
| 库存/单据 | `phone:view/report:view` | 列表 | 桌面表格 | `/inventory/phones`, `/documents` |
| 后台管理 | `user:manage/role:manage/audit:view` | 用户、角色、组织、地点、审计 | 同等模块 | `/admin/*` |
| 离线草稿 | 登录用户 | 本地队列与重试 | 本地队列与重试 | 原业务接口 |
| 个人设置 | 登录用户 | 姓名、用户名、密码 | 姓名、用户名、密码 | `/auth/profile`, `/auth/password` |

共同规则：页面和阶段按权限显示；来源地点按权限数据范围过滤；金额字段由后端 `report:view` 范围控制；库存变化只通过领域单据接口；扫码操作保持幂等键；无扫码需求的阶段（建立接收单、确认销售、维修接收）不强制扫描。
