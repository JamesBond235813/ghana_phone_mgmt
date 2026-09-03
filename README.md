# 深圳—加纳二手手机流转管理系统

这是系统的开发工作区，设计基线见 [系统设计文档](docs/SYSTEM_DESIGN.md)。

当前已完成：

- FastAPI 后端骨架、健康检查接口；
- 手机号密码登录和手机号验证码登录的 API 占位；
- 可替换的短信服务适配器边界；
- Vue 3 + Vite 手机端工作台原型；
- PWA Manifest、Service Worker 和添加到手机桌面的配置；
- 基础项目忽略规则和前后端启动说明。
- IMEI、托盘—箱子关系、深圳发运、加纳接收验收、门店调拨、销售、退回、维修和盘点的后端业务接口；
- 手机端 PWA 对上述现场任务的扫码/手工录入表单和权限过滤。

当前仍属于上线前试运行版本：短信运营商适配、Refresh Token、照片附件、复杂离线冲突审批、完整审计报表和生产 MySQL 部署验证需要继续完成。超级管理员可使用后端初始化命令创建，命令要求显式指定数据库并隐藏读取密码。用户/角色/组织后台已实现查询、创建以及用户和角色的基础维护接口；库存和单据查询已按权限隐藏金额字段。后续开发必须以设计文档中的 IMEI、容器关系、业务状态机、角色权限和不可变库存流水为准。

## 启动前端

```bash
cd /Volumes/little_server/ghanaPhone_management/frontend
npm install
npm run dev
```

## 启动后端

```bash
cd /Volumes/little_server/ghanaPhone_management
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

健康检查地址：`http://127.0.0.1:8000/health`
