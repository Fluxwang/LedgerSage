# 02 · SQLite 数据层与表结构

Status: open
Milestone: M1
Blocked by: 01

## 背景

SQLite 只存用户、会话、Agent 推理轨迹；账务数据一概不进库（ADR-0005）。LangGraph checkpointer 会在同一个库里自建表，schema 不由我们控制（ADR-0007）。

## 要做什么

自有表：

- `users`：`id`, `username`(unique), `password_hash`, `ledger_path`, `created_at`
- `user_settings`：`user_id`, `account_distinguation_range`, `currency`, `confidence_threshold`
- `invite_codes`：`code`, `used_by`, `used_at`, `created_at`
- `sessions`：`id`, `user_id`, `thread_id`, `title`, `created_at`, `last_active_at`
- `runs`：`id`, `session_id`, `user_id`, `intent`, `status`, `model`, `total_ms`, `total_tokens`, `created_at`
- `run_steps`：`id`, `run_id`, `seq`, `kicker`, `title`, `duration_ms`, `payload`(JSON), `created_at`

其他：

- 选定并接入迁移方案（建议 alembic；若嫌重，用带版本号的 SQL 脚本目录）。
- 数据库文件位于 `data/app.sqlite`，与 checkpointer 同库。

## 完成标准

- 首次启动自动建表；重复启动幂等。
- `run_steps.kicker` 的取值域与设计稿一致：`PARSE` / `CLASSIFY` / `TOOL` / `ASK` / `REPLY`。

## 注意

`ledger_path` 为空表示「用模板生成的默认路径」，非空表示接管的存量账本（见票 04）。
