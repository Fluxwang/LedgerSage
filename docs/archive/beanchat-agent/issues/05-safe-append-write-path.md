# 05 · 写入安全改造：纯 append + per-ledger 锁 + git commit/revert

Status: open
Milestone: M1
Blocked by: 04

## 背景

**本票是数据安全，不是优化，不可推迟。** 三个现存缺陷：

1. `bootstrap.py:49-52` 在**进程启动时**算死 `%m-expenses.bean`，服务跨月后仍往上个月文件里写。
2. `append_transaction` 追加后调 `bean-format -o <同一文件> <同一文件>`——整个文件读入再整体写回。两个并发写会用旧快照覆盖掉对方，**静默丢数据**。
3. `bean-format` 失败时（`check=True`）数据已经写进文件了，异常抛在半路。

见 ADR-0002、ADR-0003。

## 要做什么

- 写入目标文件改为**每次写入时**按当前日期计算，不再是启动时算死的属性。
- 去掉 `bean-format` 子进程调用；`EntryPrinter` 的输出直接 append 即可。
- per-ledger 的 `asyncio.Lock`（按 `user_id`），写操作在 threadpool 执行。
- 写入成功后 `git add <本次写入的那一个文件>` + `git commit`，提交信息统一格式（能区分 Agent 写入与人工提交）。**绝不 `git add -A`**——用户可能正在手工编辑其他文件。
- 撤销 API：对指定 commit 执行 `git revert`，并重载账本。
- 保留一个独立的手动维护命令跑 `bean-format`（不在写入路径上）。

## 完成标准

集成测试（`tmp_path` 造最小账本 + `git init`）覆盖：

- 并发两笔写入同一账本，两笔都在，文件未被截断。
- 服务在 8 月启动、模拟时间到 9 月，第二笔写进 `09-expenses.bean`。
- 写入后 `git log` 恰好多一个 commit，且只含那一个文件。
- 撤销后账本回到写入前状态，且账本仍可 `loader.load_file`。
- 账本目录里有用户手工改动的其他文件时，Agent 的 commit **不包含**它们。

## 注意

进程内锁跨不了进程 —— uvicorn 必须 `--workers 1`，这条要写进 README 和 compose 文件的注释里。
