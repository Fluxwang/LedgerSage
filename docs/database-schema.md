# LedgerSage 数据库表结构

`data/app.sqlite` 一共有 11 张表，分成三类。它只存非账务数据，账本本身在每个用户自己的目录里。

## 概览

| 分类      | 数量 | 表                                                                                           | 谁创建的                                                |
| --------- | ---- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 业务表    | 8    | users、user_settings、invite_codes、sessions、runs、run_steps、pending_writes、saved_queries | `beanbot/storage/migrations/*.sql`                      |
| 迁移管理  | 1    | schema_version                                                                               | `Database.__init__`                                     |
| LangGraph | 2    | checkpoints、writes                                                                          | `AsyncSqliteSaver`（`beanbot/services/agent/graph.py`） |

## 业务表

这 8 张表是项目自己的数据，由 `migrations/` 里的 SQL 文件创建。

| 表名             | 存什么                                                 | 关键字段                                                                                                                                                  | 来源迁移                   |
| ---------------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| `users`          | 用户账号                                               | `username`（唯一）、`password_hash`、`ledger_path`（这个用户的账本文件放在哪）                                                                            | 001                        |
| `user_settings`  | 用户偏好，一个用户一行                                 | `currency`（默认 CNY）、`confidence_threshold`（默认 0.7）、`account_distinguation_range`（默认 `[2,4]`）                                                 | 001                        |
| `invite_codes`   | 注册邀请码                                             | `code`（主键）、`used_by`（谁用了，空表示未使用）、`used_at`                                                                                              | 001                        |
| `sessions`       | 对话会话，相当于一个聊天窗口                           | `user_id`、`thread_id`、`title`、`active_run_id`（当前正在跑的 run）、`pending_at`                                                                        | 001                        |
| `runs`           | 用户每发一条消息，Agent 运行一次，就是一条 run         | `session_id`、`intent`（识别出的意图）、`status`（running / interrupted 等）、`model`、`total_ms`、`total_tokens`、`title`、`message`（用户原话）         | 001，003 加了 `message` 列 |
| `run_steps`      | 每次 run 的时间线步骤，大致一个 LangGraph 节点对应一条 | `run_id`、`seq`（第几步）、`kicker`（PARSE / CLASSIFY / TOOL / ASK / REPLY）、`title`、`duration_ms`、`payload`（JSON）                                   | 001                        |
| `pending_writes` | Agent 生成、等用户确认的账本修改；确认后留作审计痕迹   | `kind`（record 记账 / budget 预算）、`payload`、`status`（pending / confirmed / rejected / expired）、`commit_sha`（指向账本里的那次提交）、`resolved_at` | 002                        |
| `saved_queries`  | 用户收藏的常用查询                                     | `question`（同一用户下唯一）、`run_id`（当初回答这个问题的那次 run）                                                                                      | 004                        |

索引：`runs(user_id, created_at)`、`pending_writes(user_id, status, created_at)`、`saved_queries(user_id, created_at)`，都是为了按用户、按时间查列表。

## 迁移管理：schema_version

`schema_version` 只有一列 `version`，记录哪些迁移文件已经执行过，保证每个迁移只跑一次。

每次创建 `Database` 时（`beanbot/storage/database.py` 的 `__init__`）：

1. 建表 `schema_version`（已存在就跳过）
2. 把已执行的编号查成一个 set，比如 `{1, 2}`
3. 按文件名顺序遍历 `migrations/*.sql`，从文件名取编号：`002_pending_writes.sql` → `2`
4. 编号不在 set 里就执行这个文件，再把编号写进 `schema_version`
5. 最后把 `runs` 里状态还是 `running` 的记录改成 `interrupted`（上次异常退出留下的）

| 迁移文件                 | 做了什么                                                         |
| ------------------------ | ---------------------------------------------------------------- |
| `001_initial.sql`        | 建 users、user_settings、invite_codes、sessions、runs、run_steps |
| `002_pending_writes.sql` | 建 pending_writes                                                |
| `003_run_message.sql`    | 给 runs 加 `message` 列                                          |
| `004_saved_queries.sql`  | 建 saved_queries                                                 |

新增表或列时，加一个 `005_xxx.sql`，下次启动会自动只跑这一个。

## LangGraph 的表

这两张表不在 migrations 里，是 `graph.py` 里的 `AsyncSqliteSaver` 自动创建的。它和 `Database` 用同一个 `settings.database_path`，所以在同一个文件里。

| 表名          | 存什么                                                   |
| ------------- | -------------------------------------------------------- |
| `checkpoints` | 图运行到每一步时的状态快照；追问后靠它从中断的地方继续跑 |
| `writes`      | 节点执行中途写入的数据，配合 checkpoints 使用            |

和 `run_steps` 的区别：`run_steps` 是给用户看的时间线，只记映射表里有的节点；checkpoints 是给 LangGraph 恢复状态用的，不要手动改。

## 表之间的关系

箭头方向：被引用的表 → 引用它的表（外键方向）。

```
users ─┬─→ user_settings
       ├─→ invite_codes   (used_by，可为空)
       ├─→ sessions ─→ runs ─┬─→ run_steps
       │                     ├─→ pending_writes
       │                     └─→ saved_queries
       ├─→ pending_writes
       └─→ saved_queries
```

users 是所有业务表的根；sessions → runs → run_steps 是一次对话从窗口到步骤的三层。runs 还通过 `user_id` 直接引用 users，图中省略。schema_version 和 LangGraph 的两张表不和它们建外键。

## 备注

- 每个用户的账本目录下还有一个独立的 `vector.sqlite`（如 `data/ledgers/<id>/vector.sqlite`），是另一个数据库，不算在这 11 张里。
- 所有连接都开了 `PRAGMA foreign_keys=ON`，所以上面的外键会真正生效。
- 本地库如果还没有 `saved_queries`，说明 004 迁移之后服务还没重启过，下次启动会自动建。
