# 2026-09-03 角色合并前端调整总结

## 本轮目标

按照新的岗位分工，将前端作业入口从多个零散权限卡片调整为岗位连续作业：

- 深圳综合仓作业员：收购验收、装入托盘、装箱封存；
- 深圳发运员：保持独立发运入口；
- 加纳综合仓作业员：到货验收、仓库拣货调拨、退回分诊、维修建单和 QA；
- 维修技师：保持独立维修接收/维修结果入口（当账号拥有对应权限时）。

## 已完成

### 1. PC 与手机端岗位聚合入口

- 新增“深圳收购仓作业”综合卡片，按“收购验收 → 装入托盘 → 装箱封存”显示步骤条。
- 新增“加纳综合仓作业”综合卡片，按权限显示“建立到货单 → 逐台到货验收 → 门店拣货调拨 → 退回分诊 → 建立维修单 → 维修 QA 复核”等步骤。
- 当账号具备完整合并岗位能力时，隐藏其组成的旧分散卡片，避免同一岗位看到重复入口；未完成合并的历史/部分权限账号仍保留原入口。
- 发运、销售、门店收货、盘点等非本次合并岗位仍按原权限显示。

### 2. 扫码与现场交互

- 装托盘/装箱步骤要求先扫描或输入目标托盘/箱子编码，再连续扫描手机 IMEI 或托盘编码。
- 手机端使用摄像头扫描目标容器后自动切换到批量明细扫描，并保留手工输入和“重扫”操作。
- PC 端扫码枪输入框支持先录目标容器，再按 Enter 连续录入明细。
- 工作流步骤切换时重新校验地点范围；例如从加纳管理处切换到维修区时，不会错误沿用无权限地点。
- 每个步骤仍调用既有后端 API，并保留独立单据、幂等键、离线草稿和审计语义。

### 3. 权限与元数据兼容

- 聚合入口主要依据权限集合判断：
  - 深圳：`purchase:create`、`tray:manage`、`box:manage`；
  - 加纳：`receiving:unpack`、`receiving:accept`、`transfer:create`、`return:receive`、`repair:create`、`repair:approve`。
- 同时兼容后端将来在 `/auth/me` 返回的 `work_group`、`role_codes`、`roles` 元数据；元数据可优先指定岗位工作组，权限仍控制具体步骤显隐。
- `frontend/src/api.ts` 的 `CurrentUser` 增加了上述可选字段，兼容旧后端响应。

### 4. 文档与样式

- 更新手机端和 PC 端 README，记录合并岗位步骤及扫码顺序。
- 增加 PC/手机工作流步骤条、岗位提示、下一步提示和容器先扫样式。

## 验证

- `frontend`: `npm run build` 通过；Vite/PWA 仅保留原有大 chunk 警告。
- `frontend-pc`: `npm run build` 通过。
- `git diff --check` 通过。

## 相关文件

- `frontend/src/App.vue`
- `frontend/src/api.ts`
- `frontend/src/style.css`
- `frontend-pc/src/App.vue`
- `frontend-pc/src/style.css`
- `frontend/README.md`
- `frontend-pc/README.md`

## 后端对接说明

前端不依赖具体角色代码即可工作；推荐后端 `/auth/me` 返回规范角色的 `work_group`/`role_codes`，例如 `SHENZHEN_OPERATIONS`、`GHANA_OPERATIONS`。实际角色、权限并集、地点数据范围和数据库迁移由后端角色合并实现负责。
