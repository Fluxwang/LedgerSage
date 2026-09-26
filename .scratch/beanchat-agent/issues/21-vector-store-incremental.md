# 21 · 向量库 per-user 化与增量更新

Status: open
Milestone: M3
Blocked by: 11

## 背景

现状三个问题：`config.yaml` 没有 `db_store_folder`，`sqlite_store.py:30` 静默落到 `"."`，向量库躺在进程工作目录；`vector_service.py:85` 用 `transaction_amount`=200 截断，库里只有最近 200 笔；建库是手动触发的（Telegram 的 `/build_db`，该入口即将消失）。

## 要做什么

- 路径改为 `data/ledgers/<user_id>/vector.sqlite`，随账本走。
- 写入成功后**异步 fire-and-forget** 把该笔 embed 并插入，不阻塞回复。
- 保留全量重建：后台任务 + 一个管理端点，用于初次导入（接管存量账本时必须跑一次）和异步失败后的修复。
- **取消 200 条截断**——增量更新之后没有理由再截断。
- 首次登录若向量库为空，提示用户触发一次全量构建，并显示进度。

## 完成标准

- 两个用户的向量库互不可见。
- 记一笔之后立刻再记同类的一笔，召回里能出现前一笔。
- 全量重建可中断、可重跑、幂等。
- 异步 embed 失败只写日志，不影响记账成功。
