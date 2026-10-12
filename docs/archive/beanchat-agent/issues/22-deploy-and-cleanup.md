# 22 · 生产镜像、compose 与旧代码清理

Status: open
Milestone: M3
Blocked by: 19, 20, 21

## 背景

收尾票。前面几票刻意保留了一批已经作废但还能跑的旧代码，统一在这里删。

## 要做什么

**部署**

- 多阶段 `Dockerfile`：node 阶段 `vite build` → python 阶段装依赖并拷入前端产物，由 `StaticFiles` 托管。
- 镜像需含 `git`（ADR-0003）；**不需要** `bean-format`（ADR-0002）。
- `docker-compose.yml`：一个服务 + `ledgers/` 与 `data/` 两个卷。
- **`uvicorn --workers 1`，并在 compose 与 README 里注明原因**（进程内锁，ADR-0002）。

**清理**

- 删 `bots/telegram_bot.py`、`bots/controller.py`、`services/parser.py`。
- 删 `ledger_service.generate_transactions` 的 RAG / 向量兜底链、`vector_service.modify_args_via_vector`、`services/rag_client.py`。
- 删 `models.py` 里的 `ErrorMessage` / `BaseMessage`（`Table` 保留）。
- `requirements.txt` 移除 `python-telegram-bot`、`flask`、`flask-babel`、`fava`、`beangulp` 等不再使用的依赖。
- `i18n.py` 的定位重新确认（错误文案在 API 层还是 service 层本地化）。

**文档**

- README / README_ZH 重写：新架构分层、环境变量、部署方式、单 worker 约束；Roadmap 里的 Flask 两条替换为实际情况。
- `CLAUDE.md` 同步更新（它描述的 `gateways → services → controller → bots` 分层已不成立）。

## 完成标准

- 全新机器上 `docker compose up` 后能注册、登录、记账、查询、看仪表盘。
- `grep -r "get_context\|BotController\|parse_args" beanbot/` 无结果。
- 测试全绿。

## 注意

**账本卷的备份机制仍未决定**——容器化后 `ledgers/` 是唯一真源，本地 git 与卷同生共死。上线前需要单独决策（定期 push 远程 / 定期打包外传）。
