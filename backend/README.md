# Backend

开发环境启动：

```bash
cd /Volumes/little_server/ghanaPhone_management
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

当前 Alembic head 为 `0008_usernames`，包含幂等记录、盘点差异审核表、后台查询结构和用户名登录字段。

数据库迁移：

```bash
cd /Volumes/little_server/ghanaPhone_management/backend
../.venv/bin/alembic upgrade head
```

初始化或更新超级管理员时，必须显式指定应用数据库连接串；密码在终端隐藏输入，不写入代码或日志：

```bash
cd /Volumes/little_server/ghanaPhone_management/backend
PYTHONPATH=. ../.venv/bin/python scripts/bootstrap_super_admin.py \
  --database-url "$DATABASE_URL" --username <管理员用户名>
```

该命令可重复执行，会确保超级管理员账号、全部权限和全局数据范围存在，不会连接未明确指定的数据库。

执行迁移前请通过环境变量 `DATABASE_URL` 或 `.env` 配置目标数据库；不要把真实密码提交到代码库。

初始迁移用于建立开发基线，后续生产变更应生成显式 Alembic migration；不要在生产环境随意执行 `downgrade`，因为初始迁移的回滚会删除模型表。
