# 本轮项目拉取与本地启动总结

## 完成内容

- 将 `JamesBond235813/ghana_phone_mgmt` 仓库拉取到当前目录，并以 `/Users/jackbond/Desktop/ghana_phone_mgmt` 作为项目根目录。
- 创建 Python 虚拟环境 `.venv`，使用本机 Python 3.12 安装 `backend/requirements.txt`；项目代码使用 `enum.StrEnum`，因此不能使用系统 Python 3.9。
- 安装前端依赖（`frontend/npm install`）。
- 在本地 MySQL 创建数据库 `ghana_phone`（utf8mb4）。
- 执行 Alembic 数据库迁移。仓库的 `0001_initial_schema` 会按当前模型创建 `users.username`，而 `0008_usernames` 又重复添加该列，首次迁移因此出现重复列错误；检查确认列、唯一索引及手机号可空属性均已存在后，将 Alembic 版本安全标记为 `0008_usernames`，未重复改表。
- 最终数据库包含 39 张表，Alembic 当前版本为 `0008_usernames`。
- 通过 detached screen 会话启动：
  - `ghana-phone-backend`：FastAPI/Uvicorn，`127.0.0.1:8000`
  - `ghana-phone-frontend`：Vite，`127.0.0.1:5173`

## 验证结果

- `GET http://127.0.0.1:8000/health` 返回 HTTP 200：`{"status":"ok","service":"Ghana Phone Management"}`。
- `GET http://127.0.0.1:5173/` 返回 HTTP 200，Vite 页面正常响应。
- `frontend` 执行 `npm run build` 成功，PWA 资源正常生成；仅有常规的 bundle 大小提示。

## 当前运行与配置

- 数据库连接配置写入 `backend/.env`，该文件不应提交到 Git；其中包含本机开发环境连接信息。
- 可用 `screen -ls` 查看会话；停止服务可分别执行 `screen -S ghana-phone-backend -X quit` 和 `screen -S ghana-phone-frontend -X quit`。
- 原 Python 3.9 虚拟环境已保留为 `.venv-py39`，当前项目使用 `.venv`（Python 3.12）。

