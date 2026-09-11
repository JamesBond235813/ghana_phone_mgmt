# 本轮任务总结：岗位合并后端落地

日期：2026-09-03
项目：`/Users/jackbond/Desktop/ghana_phone_mgmt`

## 完成内容

- 新增规范岗位：`demo_sz_operations`（深圳收购验收、装托盘、装箱）、
  `demo_sz_dispatch`（深圳发运）、`demo_ghana_operations`（加纳到货验收、仓库拣货/调拨发运、退回分诊、维修建单与 QA），并保留 `demo_repair_tech` 为独立维修技师。
- `Role` 增加 `is_active`、`work_group`、`description`，支持岗位归档和客户端按工作组展示。
- 新增 Alembic `0009_merge_operational_roles`：将旧角色权限合并、重挂用户角色、旧角色归档为 inactive 且清空权限；不删除用户。
- 新增 `0010_ghana_dispatch_boundary`：明确国际 `shipment:dispatch` 仍为深圳职责，加纳门店配送使用 `transfer:create` + `inventory:issue`。
- 演示种子改为 10 个规范岗位账号：`szops`、`szdispatch`、`ghops`、`storeareceive`、`storeaclerk`、`storeasupervisor`、`storeboperator`、`returnpack`、`repairtech`、`auditor`；旧 8 个演示账号保留但停用并指向规范角色，密码哈希不删除。
- `ghops` 的 `phone/report/tray/box` 范围覆盖管理处和维修区；收发/调拨/退回权限限管理处，维修建单和 QA 限维修区。
- `/auth/me`、密码登录和 `/admin/roles` 增加角色、工作组、操作元数据；后台默认只返回 active 角色，拒绝把 inactive 角色分配给新用户。
- 权限查询仅汇总 active 角色，避免归档角色残留权限生效。

## 验证

- 本地 Alembic 版本：`0010_ghana_dispatch_boundary (head)`。
- 种子脚本重复执行成功；当前 active demo 角色 10 个、active demo 账号 10 个，超级管理员 `xiaojiang` 未改变。
- 后端测试：`19 passed`。
- `git diff --check` 通过。

## 运维命令

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt/backend
PYTHONPATH=. ../.venv/bin/alembic upgrade head
PYTHONPATH=. ../.venv/bin/python scripts/seed_demo_data.py
```

本地测试密码不写入项目文档；正式管理员接口仍要求至少 8 位密码。角色拆分回滚不能自动推断每个用户的原岗位，`0009` 的 downgrade 因此保持 no-op，若要回滚需人工审查用户分配。
