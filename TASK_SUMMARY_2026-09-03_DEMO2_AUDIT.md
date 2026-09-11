# DEMO2 重跑与退回/维修数据一致性审计总结

日期：2026-09-03

## 本轮目标

在本地 MySQL `ghana_phone` 上重跑演示数据，并重点核对退回接收、退回分诊、维修建单相关的箱/托盘快照、手机当前托盘关系、单据状态和库存流水是否还残留旧版本数据；同时复核跨地点维修建单 API 的幂等和容器边界。

## 执行与结果

- 在 `backend/` 连续执行 `PYTHONPATH=. ../.venv/bin/python scripts/seed_demo_data.py` 多次，均成功；脚本输出 52 台手机、15 个托盘、10 个箱子、10 个岗位账号。
- DEMO2 数据最终规模：2 个组织、5 个地点、10 个箱子、15 个托盘、52 台手机。
- 活动手机—托盘关系 32 条、活动托盘—箱关系 11 条；每台演示手机的 `status`、组织、地点、`current_tray_id` 与活动关系均一致。
- 演示库存流水共 279 条，`demo2-phone:*` 幂等键无重复；279 条包含显式的“退回分诊拆托”步骤，顺序可还原。
- 所有 DEMO2 单据编号集合和状态均符合当前样本设计：在途/接收中/已完成、待审核、处理中、待验收等没有旧状态残留。

## 发现并处理的旧数据

早期样本版本曾在 `DEMO2-REP-SUBMITTED` 下留下多余的维修容器快照。`seed_demo_data.py` 的 `upsert_return` 与 `upsert_repair` 现在会对 DEMO2 单据的容器和手机明细做收敛清理：只保留本版本声明的精确行，并移除旧版本遗留行；不会删除没有 DEMO2 前缀的业务数据。

最终退回/维修子表如下：

| 单据 | 容器快照 | 手机明细 |
| --- | --- | --- |
| `DEMO2-RET-STORE-A-TRANSIT` | `BOX / DEMO2-BOX-RETURN-TRANSIT` | 1 台（43） |
| `DEMO2-RET-STORE-A-RECEIVED` | `BOX / DEMO2-BOX-RETURN-RECEIVED` | 1 台（44） |
| `DEMO2-REP-SUBMITTED` | `TRAY / DEMO2-TRAY-RETURN-RECEIVED`（来源托盘快照） | 1 台（44） |
| `DEMO2-REP-ACTIVE`、`DEMO2-REP-QA`、`DEMO2-REP-DONE` | 无旧容器残留 | 各 1 台 |

维修单上的 `DEMO2-TRAY-RETURN-RECEIVED` 是管理处开托时的来源快照；手机随后通过分诊流水进入维修区的 `DEMO2-TRAY-REPAIR`。这两个概念不应混为“把退回托盘搬到维修区”。

## 低风险代码修正

1. `backend/app/domain/repair_service.py`：跨地点退回分诊扫描箱子时，除检查外箱存在、启用、地点和非空外，还逐个校验箱内托盘仍启用且位于退回接收地点，阻断陈旧 `current_box_id` 把维修区托盘伪装成管理处来源物料。
2. `backend/app/domain/container_service.py` 与 `backend/app/api/inventory.py`：`PHONE` 容器/装托入口统一支持 IMEI1/IMEI2 别名，避免双卡手机扫描 IMEI2 时在装托、拆托、整单或维修分诊路径报“IMEI 不存在”。
3. 新增回归测试覆盖“箱内托盘地点错误”拒绝、IMEI2 容器展开和 IMEI2 装托 API。

本轮没有新增或修改数据库表结构、迁移，也没有清理非 DEMO2 数据。

## 验证命令

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt/backend
PYTHONPATH=. ../.venv/bin/pytest -q
```

结果：`22 passed, 2 warnings`。

另外执行 `git diff --check`，无输出且通过。前端构建结果沿用本轮前置验证：`frontend` 与 `frontend-pc` 均已构建成功。

## 后续注意

- 维修建单 API 的同一 `X-Idempotency-Key` 重试和跨用户/跨操作冲突已有测试；并发请求的数据库唯一键竞争仍应在后续统一幂等中间件中处理。
- 当前 `repair_orders.return_order_id` 仍是一对一约束；同一退回单拆成多个维修批次时，需要另行设计分诊批次模型，不能靠重复建单绕过约束。
