# 19 · 预算：`custom "budget"` 读写与 budget 意图

Status: open
Milestone: M3
Blocked by: 18

## 背景

预算数据也写回 ledger 文件，不进数据库。Beancount 无原生预算指令，采用 fava-envelope 的既有约定。见 ADR-0008。

## 要做什么

- 读：遍历 `entries` 取 `data.Custom`，`type == "budget"` 的解析成 `(account, period, amount, currency, effective_date)`；同一账户取日期最新的那条生效。
- 写：`set_budget` 工具，**追加**一行到 `budgets.bean`（不改写旧行），复用票 05 的锁与 git commit 路径。
- 图上接通 `budget` 意图分支；金额或账户不明确时走 Ask。
- 仪表盘与查询回复中展示预算执行情况（已用 / 上限 / 剩余）。
- 模板脚手架要包含 `budgets.bean` 并在 `main.bean` 里 include（票 04 若未做则在此补）。

## 完成标准

- 「给餐饮设个每月2000的预算」→ `budgets.bean` 多一行，`git log` 多一个 commit。
- 「把餐饮预算调到2500」→ 再多一行，读取时生效值为 2500，旧行仍在。
- 账本仍可被 `loader.load_file` 正常加载，无新增 error。
