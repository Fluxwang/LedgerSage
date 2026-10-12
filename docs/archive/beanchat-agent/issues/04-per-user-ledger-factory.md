# 04 · per-user 账本工厂与模板脚手架

Status: open
Milestone: M1
Blocked by: 03

## 背景

现有 `bootstrap.py` 把一切塞进模块级全局 `AppContext`，`get_context()` 直取。`BeancountRepository` 持有 `filename` / `write_filename` / `mtimes` / `_entries`，天生是「一本账本一个实例」，全局单例在 per-user 账本下不成立（ADR-0005）。

## 要做什么

- 拆分 `AppContext`：无状态的（配置、logger、LLM 客户端、embedding 客户端）留全局；`BeancountRepository`、`VectorStore`、`LedgerService` 改为按 `user_id` 取的带 LRU 缓存的工厂。
- FastAPI `Depends` 注入 per-user 依赖，不再有 `get_context()` 直取。
- 账本模板脚手架：`main.bean` + `accounts/{assets,liabilities,expenses,income,equity}.bean` + 当年目录 + `budgets.bean`，账户 `open` 指令带 `name:` meta（见 ADR-0009）。
- 注册时在 `data/ledgers/<user_id>/` 生成模板并 `git init`（含首次 commit）。
- `users.ledger_path` 非空时跳过脚手架，直接接管该路径；接管时校验路径存在、是 git 仓库（不是则 `git init`）、`main.bean` 可加载。

## 完成标准

- 两个用户并存时，各自 `repository.accounts` 互不可见。
- 缓存驱逐后重新加载账本不丢数据、不串号。
- 新注册用户能立刻记账（模板里有足够的 `open` 指令供 `find_account` 命中）。

## 注意

`/mnt/f/Beancount` 作为接管路径接进来当第一个用户——它的账户命名与模板不同，两条路的 Agent 行为会有细微差别，这是已知且接受的。
