# 07 — 账户前缀规范化、按段匹配

**What to build:** 账户前缀现在是按字符串匹配的。`Expenses:Fo` 能匹配到 `Expenses:Food:Dining`，`Expenses:Food` 还会顺带匹配到 `Expenses:FoodDelivery`。按 `CONTEXT.md` 的「账户」词条，前缀改为**按段**匹配：账户等于 `p`，或者账户以 `p + ":"` 开头，才算匹配。匹配之前先规范化：去掉首尾空白和末尾的 `:`，规范化后为空串时视为不筛选。

三个工具（`query_transactions`、`get_balance`、`list_accounts`）共用同一个规范化函数和同一个判断函数，这样后续 08 的校验和真正执行的查询用的是同一套规则。

详见 spec 的「查询账户前缀」一节。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 新增「规范化前缀」和「账户是否落在前缀下」两个函数，放在账本网关或查询模块里，所有用到的地方都调用它们
- [ ] `query.py` 里交易查询和余额查询的两处正则，从 `^前缀` 改为 `^前缀(:|$)`，前缀仍然要转义
- [ ] `ledger.py` 中 `query_transactions` 的 `startswith`，以及 `graph.py` 中 `list_accounts` 的 `startswith`，都改用按段判断
- [ ] `Expenses:` 等价于 `Expenses`；` Expenses:Food ` 等价于 `Expenses:Food`；`:` 和空串都视为不筛选
- [ ] 测试覆盖：`Expenses:Food` 能命中 `Expenses:Food:Dining`，不能命中 `Expenses:FoodDelivery`；`Expenses:Fo` 什么都不命中；末尾带冒号的前缀和不带的结果一样；三个工具的行为一致
- [ ] 现有测试里 `account_prefix='Expenses:'` 的用例照常通过
- [ ] `pytest` 通过
