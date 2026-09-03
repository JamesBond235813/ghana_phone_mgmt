# PC 端进销存工作台

独立的 Vue 3 + Vite 桌面端前端，复用现有 FastAPI 接口、权限、数据范围和业务流转。左侧导航按账号权限显示，右侧为扫码枪和业务作业区。

已覆盖采购入库、装托盘、装箱、发运出库、接收验收、门店调拨、销售、销售退回、维修、盘点、IMEI 查询、库存、单据、离线草稿、用户/角色/组织/地点管理、审计和个人资料。

```bash
cd /Volumes/little_server/ghanaPhone_management/frontend-pc
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5174`。扫码枪按键盘输入设备使用：将光标放在扫码输入框，扫码枪通常会自动发送 Enter，IMEI 即加入列表。生产部署时可通过 `VITE_API_BASE_URL` 指向后端 API。
