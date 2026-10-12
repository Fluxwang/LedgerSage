# 01 · FastAPI 骨架与 pydantic-settings 配置层

Status: open
Milestone: M1
Blocked by: —

## 背景

现有 `settings.py` 的 `__getattr__` 在 key 不存在时返回空 `Settings`（假值但非 `None`），漏写配置静默降级——`config.yaml` 从未定义 `db_store_folder`，向量库因此落到进程工作目录。见 ADR-0011。

## 要做什么

- 新增 `beanbot/config.py`：`pydantic-settings` 的 `BaseSettings`，字段含数据目录、账本根目录、JWT secret、邀请码、LLM `base_url`/`api_key`/`model`、embedding 配置、置信度阈值。
- 删除 `beanbot/settings.py` 与 `ImmutableDict`。
- 新增 `beanbot/api/app.py`：FastAPI 应用工厂，挂载全局异常处理器（把领域异常映射成带状态码的 JSON）。
- 新增 `beanbot/exceptions.py`：`AccountNotFound`、`LedgerWriteConflict`、`ClarificationTimeout`、`InvalidInviteCode` 等领域异常基类与状态码映射。
- 开发用 `docker-compose.dev.yml` + `.env.example`（不含真实密钥）。
- `requirements.txt` 拆成 `requirements.txt` / `requirements-dev.txt`，新增 `fastapi`、`uvicorn`、`pydantic-settings`、`langchain`、`langgraph`、`langchain-openai`、`python-jose`、`passlib[bcrypt]`。

## 完成标准

- 缺任一必填环境变量时，应用**启动即失败**并指名缺了哪个。
- `GET /health` 返回 200。
- 现有 `config.yaml` 不再被任何代码读取。

## 注意

`.env` 已在 `.gitignore` 里。`config.yaml` 里有真实密钥，迁移时逐个搬到 `.env`，不要把值写进任何被跟踪的文件。
