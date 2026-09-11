# 合并岗位后的数据库、权限与 API 校验说明

更新时间：2026-09-03

本文是对本轮岗位合并要求的后端核对结果。它与《岗位 SOP、交接与权限设计》配套使用，重点说明数据库中怎样表达综合岗位、API 怎样校验地点，以及前端菜单应依赖哪些权限。

## 1. 合并后的岗位边界

| 岗位代码（建议） | 现场职责 | 功能权限并集 | 允许的地点范围 |
|---|---|---|---|
| `demo_sz_operations` | 深圳收购验收、装托盘、装箱 | `phone:view`、`phone:edit`、`purchase:create`、`tray:manage`、`box:manage` | 深圳仓/收货区 |
| `demo_sz_dispatch` | 深圳发运 | `phone:view`、`shipment:view`、`shipment:dispatch`、`inventory:issue` | 深圳仓/发运区 |
| `demo_ghana_operations` | 加纳到货验收、管理处拣货发运、退回分诊、维修建单、维修 QA | `phone:view`、`shipment:view`、`receiving:unpack`、`receiving:accept`、`tray:manage`、`box:manage`、`inventory:receive`、`transfer:create`、`inventory:issue`、`return:receive`、`repair:create`、`repair:approve`、`report:view` | 管理处仓/接收区 + 维修区；每项权限仍按具体地点限制 |

门店收货、门店销售/主管、门店 B 串货、门店退回打包、维修技师、审计员等岗位保持独立。岗位代码不是前端授权依据；前端和 API 都应根据权限集合及地点范围工作。

## 2. 当前表结构是否足够

当前关系已经可以表达综合岗位，不需要把“岗位”硬编码成一个地点：

```text
users ──< user_roles >── roles ──< role_permissions >── permissions
  └──< user_scopes(permission_code, scope_kind, scope_value)
```

`UserScope` 是“用户 + 权限”的范围，而不是“用户 + 角色”的单一范围。因此同一个加纳综合岗位用户可以拥有如下多行数据：

```text
phone:view        location  GH-MGMT
phone:view        location  GH-REPAIR
receiving:accept  location  GH-MGMT
return:receive    location  GH-MGMT
repair:create     location  GH-REPAIR
repair:approve    location  GH-REPAIR
report:view       location  GH-MGMT
report:view       location  GH-REPAIR
```

`AccessContext.can_access()` 对同一权限的多个范围采用 OR 语义，故不会因为维修区和管理处是两个地点而需要复制账号或角色。数据库层仍应保持以下不变量：

1. `role_permissions` 只绑定已登记的权限代码；
2. 业务地点必须属于请求中的组织且处于启用状态；
3. 所有会改变库存的 API 除功能权限外，还必须校验资源的来源/目的地点；
4. 任何装托、装箱、收发、维修和盘点动作都通过库存流水和单据留痕，不能直接更新状态；
5. 综合岗位不应获得 `repair:receive` 或 `repair:update`，除非该组织明确让同一岗位兼任维修技师。这样可以保留“维修执行”和“维修 QA”之间的分工。

加纳综合岗位不默认拥有 `shipment:dispatch`。当前接口的语义是创建跨组织 Shipment，且只接受深圳库存/已装托盘/已装箱状态；加纳管理处向门店的实际作业应使用 `transfer:create` + `inventory:issue`。如果未来同一人员确实负责国际发运确认，应另设发运权限或增加路线/目的地约束后再授予。

本轮没有新增 `role_scopes` 表：范围属于人员在实际组织/地点中的授权，直接放在 `user_scopes` 可以支持同一个岗位在多个维修区/仓区工作，也避免给一个角色绑定全局地点后误放大权限。

## 3. API 校验约定

| 操作 | 必须的功能权限 | 地点参数应校验 |
|---|---|---|
| 深圳采购收货 | `purchase:create` | 收货组织（建议同时校验收货地点） |
| 装托盘/装箱 | `tray:manage` / `box:manage` | 当前容器地点 |
| 深圳国际发运 | `shipment:dispatch` | 起运地点（深圳发运岗位） |
| 到货开箱/逐台验收 | `receiving:unpack` / `receiving:accept` | 接收目的地点 |
| 管理处向门店拣货 | `transfer:create` + `inventory:issue` | 调拨来源地点 |
| 门店收调拨 | `transfer:receive` | 调拨目的地点 |
| 退回接收 | `return:receive` | 退回目的地点 |
| 维修建单/维修 QA | `repair:create` / `repair:approve` | 维修地点 |

收发单据列表属于交接待办，应允许拥有 `phone:view` 或 `report:view` 且对来源或目的地点有范围的人员看到；仅按来源地点过滤会导致接收员看不到发给自己的任务。详细实现见 `backend/app/api/documents.py`。

## 4. 前端依赖

前端菜单、首页工作卡片和地点选择器只依赖 `/auth/me` 返回的 `permissions` 与 `scopes`：

- 深圳综合岗位显示一张“深圳收购仓作业”连续工作卡，内部按“采购收货 → 装托盘 → 装箱封存”分步；每一步提交时仍使用自己的权限和地点范围。
- 深圳发运员只显示“发运出库”和相关在途单据，不显示采购或容器编辑入口。
- 加纳综合岗位显示“到货开箱/验收、管理处拣货发运、退回接收分诊、维修建单、维修 QA”入口；管理处操作的地点选择器只列管理处，维修入口只列维修区。
- `repair:create`、`repair:approve` 的地点选择器不得把管理处当成维修区；反之 `receiving:accept` 不得把维修区当成接收区。
- 菜单显隐只是体验优化，API 的权限和范围拒绝仍是最终安全边界。

## 5. 回归测试

`backend/tests/test_merged_role_scope.py` 覆盖：

- 深圳综合岗位功能权限并集及单地点隔离；
- 加纳综合岗位在管理处和维修区的多地点 `UserScope` OR 语义；
- `/auth/work-locations` 按所选权限返回正确的 `source_allowed`；
- 库存查询只返回授权地点的手机；
- 同一加纳综合岗位可在管理处开始接收、在维修区创建维修单并独立执行维修 QA；
- 使用错误地点调用接收 API 返回 403，业务状态机仍拒绝重复送修。

运行：

```bash
cd backend
PYTHONPATH=. ../.venv/bin/pytest -q tests/test_merged_role_scope.py
```

当前结果：3 passed（仅保留现有 Starlette/httpx 弃用警告）。

## 6. 数据迁移注意事项

合并角色时应先把现有用户的 `user_roles` 重挂到 canonical role，再处理旧角色；不能先删除旧角色，否则外键会使旧用户失去岗位关联。旧用户名若要保留登录兼容，应作为停用的 legacy 用户或显式迁移别名处理，不能让同一人员同时获得两套重复权限。迁移后应重新生成/校验每个综合岗位用户的 `user_scopes`，尤其是加纳管理处与维修区两组范围。
