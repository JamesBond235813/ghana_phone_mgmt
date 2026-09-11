# 深圳—加纳二手手机流转管理系统

这是系统的开发工作区，技术与领域基线见 [系统设计文档](docs/SYSTEM_DESIGN.md)；现场岗位、承接—作业—移交、权限、页面和验收基线见 [岗位 SOP 与交接设计](docs/ROLE_SOP_HANDOFF_DESIGN_2026-09-03.md)。后续实现以两份文档中较新的状态机、权限矩阵和不可变流水约束为准。

当前已完成：

- FastAPI 后端骨架、健康检查接口；
- 手机号密码登录和手机号验证码登录的 API 占位；
- 可替换的短信服务适配器边界；
- Vue 3 + Vite 手机端工作台原型；
- PWA Manifest、Service Worker 和添加到手机桌面的配置；
- 基础项目忽略规则和前后端启动说明。
- IMEI、托盘—箱子关系、深圳发运、加纳接收验收、门店调拨、销售、退回、维修和盘点的后端业务接口；
- 手机端 PWA 对上述现场任务的扫码/手工录入表单和权限过滤。
- 本地 `DEMO2-` 演示数据、按现场合并岗位配置的演示账号及权限范围（历史拆分账号保留为停用记录）；详情见
  [本轮岗位合并与验证总结](TASK_SUMMARY_2026-09-03_ROLE_MERGE.md)。

当前已完成的流程设计补充：

- 按现场合并岗位组织“承接、作业、移交”：深圳综合作业员一人完成收购验收/装托/装箱，加纳综合作业员承接到货、拣货调拨、退回分诊、维修建单与 QA；覆盖深圳收购到加纳管理处、门店配送、店间串货和维修退回；
- 明确托盘/箱子先扫码、手机连续扫码、每次扫描即时留痕、封存/发出/收货双人交接，以及缺失/多出/错货/破损异常闭环；
- 定义 `work_sessions`、`scan_events`、容器关系事件、预留、交接、差异和不可变库存流水的目标模型，并列出 P0–P4 实施出口。

当前仍属于上线前试运行版本：短信运营商适配、Refresh Token、照片附件、复杂离线冲突审批、完整审计报表和生产 MySQL 部署验证需要继续完成。超级管理员可使用后端初始化命令创建，命令要求显式指定数据库并隐藏读取密码。用户/角色/组织后台已实现查询、创建以及用户和角色的基础维护接口；库存和单据查询已按权限隐藏金额字段。后续开发必须以设计文档中的 IMEI、容器关系、业务状态机、角色权限和不可变库存流水为准。

## 启动前端

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt/frontend
npm install
npm run dev
```

手机端默认端口为 `5173`；PC 端位于 `frontend-pc`，默认端口为 `5174`。局域网访问时使用本机实际 IPv4 地址，例如 `http://192.168.1.192:5173/` 和 `http://192.168.1.192:5174/`。

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt/frontend-pc
npm ci
npm run dev -- --host 0.0.0.0 --port 5174
```

## 启动后端

```bash
cd /Users/jackbond/Desktop/ghana_phone_mgmt
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

健康检查地址：`http://127.0.0.1:8000/health`
