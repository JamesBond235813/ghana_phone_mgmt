# 本轮超管设置与开源系统调研总结

## 已完成

- 使用项目自带的 `backend/scripts/bootstrap_super_admin.py` 初始化/更新超级管理员：用户名为 `xiaojiang`，密码按用户要求设置，密码未写入代码、日志或总结文件。
- 通过 `POST /api/v1/auth/password` 实际验证登录成功，返回 Bearer token，用户 ID 为 1，具备超级管理员身份。
- 调研 GitHub 上的 ERPNext、Odoo、InvenTree、OCA WMS、Dolibarr、Snipe-IT，并记录仓库地址、许可证、序列号/库存流水/条码/包装能力和适配边界。
- 明确本业务应采用“托盘作业会话 + 连续 IMEI 扫描 + 事务确认 + 不可变库存流水”的流程；保留现有 FastAPI/Vue 技术栈，不直接替换成完整 ERP。
- 详细调研和改造建议见 `docs/OPEN_SOURCE_INVENTORY_RESEARCH_2026-09-03.md`。

## 当前结果

- 本地后端仍运行在 `127.0.0.1:8000`，前端仍运行在 `127.0.0.1:5173`。
- 数据库和已有业务数据未被重置；仅更新了超管账号凭据及其权限关联。
- 本轮暂未修改托盘业务代码，先完成了成熟项目对照和目标模型设计，避免在未确认容量、封存和异常复核规则前贸然迁移数据。

