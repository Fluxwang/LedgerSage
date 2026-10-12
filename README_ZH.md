# LedgerSage

LedgerSage 把自然语言消息转成可审计的 Beancount 分录。系统支持多用户、每用户一本隔离账本、追问、固定只读查询工具、预算、实时决策轨迹、仪表盘和运行历史。

账本文件始终是账务数据的唯一真源。SQLite 只保存用户、对话、LangGraph checkpoint 和决策轨迹。

## 本地运行

需要 Python 3.12+ 与 Node 20+。

```bash
cp .env.example .env
# 填好 .env 里的全部必填密钥
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cd web && npm install && npm run build && cd ..
.venv/bin/python -m beanbot serve
```

打开 <http://localhost:8000>。额外生成邀请码：`.venv/bin/python -m beanbot invite --count 3`。

配置只读环境变量。`JWT_SECRET`、`INVITE_CODE`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 必填；缺失时应用会在启动阶段列出字段。Embedding 的可选配置见 `.env.example`。

## 架构

- `beanbot/api/`：FastAPI 路由、鉴权、SSE、仪表盘、运行历史。
- `beanbot/services/agent/`：LangGraph 分类、抽取、追问、工具、回复图，以及固定查询工具。
- `beanbot/gateways/ledger.py`：每用户 Beancount 加载、纯追加写、git commit 与撤销。
- `beanbot/storage/`：带版本号的 SQLite 业务表；LangGraph checkpoint 表位于同一数据库。
- `beanbot/services/vector_index.py`：每用户增量向量索引。
- `web/`：React + Vite + TypeScript 客户端；`frontend/index.html` 保留为视觉基准。

每次账本写入都会获取进程内的 per-ledger 锁，只追加规范文本，只 stage 目标文件，并创建一个 git commit。Uvicorn 必须保持 `--workers 1`；多 worker 不能共享锁，可能造成并发写丢失。

## 验证

```bash
.venv/bin/python -m pytest
.venv/bin/python -m mypy beanbot
cd web && npm run build
```

自动测试不需要 API key。真实模型分类评测需手动运行 `python -m tests.eval.classify`。

## Docker

创建 `.env` 后运行 `docker compose up --build`。镜像会构建 React 页面、安装 git，并用单 worker 启动。`beanchat-ledgers` 卷是账务唯一真源，上线前必须配置外部备份；备份传输方案目前仍待决策。

存量账本若把显示名写在行尾注释中，请先提交干净工作区，再运行 `python -m beanbot migrate-account-names /path/to/ledger`。脚本只修改有效的 `open` 行，加载校验失败会恢复文件，并输出完整改动清单。
