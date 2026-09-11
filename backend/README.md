# Backend

开发环境启动：

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt
source .venv/bin/activate
pip install -r requirements.txt
cd backend
uvicorn app.main:app --reload
```

当前提供手机号或用户名密码登录、登录用户查询、短信登录适配层占位，以及受权限保护的组织、地点、角色和用户管理接口；业务接口必须通过领域单据和库存流水实现，不应增加任意修改库存的接口。

认证基础层已提供带随机盐的 scrypt 密码哈希、数据库用户查询、JWT Access Token 编解码、Bearer 依赖和角色权限装载。Refresh Token 持久化仍待实现。

当前业务接口已覆盖采购入库、托盘、箱子、IMEI 查询、跨国发运、加纳接收、拆箱、逐台验收、管理处向门店调拨、门店差异收货、批发/零售销售、销售退回、维修验收、按地点盘点差异记录和盘点差异审核；库存变更接口支持 `X-Idempotency-Key`，并要求有效 JWT 和对应权限/数据范围。

`GET /api/v1/auth/work-locations` 为登录员工提供启用组织/地点选择项，返回地点基础信息和按权限计算的 `source_allowed` 标记，不返回库存明细。

管理接口还提供 `GET /api/v1/admin/audits`，仅允许具备 `audit:view` 且拥有全局范围的账号查询后台操作审计；销售单据金额只有具备授权报表范围的账号可见。

当前 Alembic head 为 `0010_ghana_role_dispatch_boundary`：除用户名、幂等记录、盘点差异审核表和后台查询结构外，还包含合并岗位元数据、历史角色停用、用户角色迁移，以及“加纳调拨不等于深圳跨境发运”的权限边界。

## 本地演示数据

仓库内的 `scripts/seed_demo_data.py` 会在已迁移的数据库中幂等创建一套
`DEMO2-` 前缀的深圳—加纳流转样本（手机、托盘、箱、发运/接收/调拨、销售、
退回、维修、盘点）以及按现场合并岗位配置的演示账号。它只更新自己的演示前缀和演示
账号，不清空其它业务数据。必须从 `backend` 目录执行，以确保读取当前 `.env`：

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt/backend
PYTHONPATH=. ../.venv/bin/python scripts/seed_demo_data.py
```

演示账号统一使用本轮约定的本地测试密码（短密码仅为方便逐岗演示，禁止用于
生产环境）；既有超级管理员账号不会被该脚本覆盖。用户/角色的功能权限与
`UserScope` 数据范围会一并写入，收货岗位可按目的地地点看到入站单据。

数据库迁移：

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt/backend
../.venv/bin/alembic upgrade head
```

初始化或更新超级管理员时，必须显式指定应用数据库连接串；密码在终端隐藏输入，不写入代码或日志：

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt/backend
PYTHONPATH=. ../.venv/bin/python scripts/bootstrap_super_admin.py \
  --database-url "$DATABASE_URL" --username <管理员用户名>
```

该命令可重复执行，会确保超级管理员账号、全部权限和全局数据范围存在，不会连接未明确指定的数据库。

执行迁移前请通过环境变量 `DATABASE_URL` 或 `.env` 配置目标数据库；不要把真实密码提交到代码库。

初始迁移用于建立开发基线，后续生产变更应生成显式 Alembic migration；不要在生产环境随意执行 `downgrade`，因为初始迁移的回滚会删除模型表。
