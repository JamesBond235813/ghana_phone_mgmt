# 岗位合并：数据库、权限范围与 API 回归核对

日期：2026-09-03

## 本轮完成

- 盘点 `users`、`roles`、`role_permissions`、`user_scopes` 及库存/单据流水模型。
- 确认 `UserScope` 按“用户 + 权限 + 范围”存储，同一综合岗位可以对同一权限拥有多个地点范围，不需要新增 `role_scopes` 表。
- 明确加纳综合岗位的最小权限：管理处接收/退回/拣货使用管理处范围，维修建单和 QA 使用维修区范围；`return:receive` 仅管理处；`phone:view`、`report:view` 可双地点。
- 评估并记录 `shipment:dispatch` 不应默认授予加纳综合岗位：加纳向门店应使用 `transfer:create` + `inventory:issue`，国际 Shipment 发运保留给深圳发运岗位。
- 新增 `backend/tests/test_merged_role_scope.py`，覆盖深圳综合岗位权限并集、加纳双地点 OR 语义、工作地点选择器、库存可见性、接收地点边界和维修创建/独立 QA。
- 新增 `docs/ROLE_MERGE_SCHEMA_API_CHECK_2026-09-03.md`，记录岗位矩阵、API 校验约定、前端权限依赖和迁移注意事项。
- 修正 `backend/migrations/versions/0008_usernames.py`：兼容早期 `Base.metadata.create_all` 已提前生成 username/index 的新数据库，避免重复列/索引导致全新数据库无法升级。
- 配合 `0009_merge_operational_roles` 核验了 `Role.is_active`、`work_group`、`description` 字段迁移；在临时 MySQL 数据库完成从空库到 head 的升级和旧角色合并演练后已清理临时库。

## 验证结果

```text
PYTHONPATH=. ../.venv/bin/pytest -q
19 passed, 2 warnings

PYTHONPATH=. ../.venv/bin/pytest -q tests/test_merged_role_scope.py
3 passed, 2 warnings
```

临时 MySQL（本机 9.3.0）从空库执行 `alembic upgrade head` 成功；旧演示角色、用户和权限链接迁移到 canonical 角色的演练成功。警告为既有 Starlette/httpx 弃用提示。

## 待整合事项

- `0009_merge_operational_roles.py` 与样本数据脚本/前端应保持相同的 canonical 角色代码和最小权限；尤其确认删除 Ghana 的 `shipment:dispatch`。
- 后续若新增维修区或管理处，按权限逐条增加 `user_scopes`，不要将综合岗位直接设为全局范围。
- 前端菜单显隐只能作为体验层，API 地点校验仍是最终安全边界。

