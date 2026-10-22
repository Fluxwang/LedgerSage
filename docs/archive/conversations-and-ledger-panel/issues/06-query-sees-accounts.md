# 06 — 查询提示词带上账户表

**What to build:** 问「这个月餐饮花了多少」时，LLM 填了一个账本里不存在的前缀 `Expenses:Dining`（真名是 `Expenses:Food:Dining`），结果查询为空，回复「这个范围内没有找到记录」。根本原因是 `model.query()` 只拿到了原话和日期，没有拿到账户表，只能凭常识去猜账户名。`extract()` 和 `budget()` 都有账户表，只有查询这条路径漏掉了。

这张票让查询和记账一样，带着「账户 + 显示名」去填参数（ADR 0009：显示名本来就是喂给 LLM 的语义信号）。

详见 spec 的「查询账户前缀」一节。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 把 `AgentModel.query` 的签名改为 `query(message, accounts, today)`，`accounts` 的格式是 `list[tuple[str, str | None]]`，和 `extract()` 保持一致
- [x] 提示词里列出账户和显示名，并要求 `account_prefix` 必须是其中某个账户，或某个账户按段计算的前缀
- [x] `graph.py` 的 `query()` 从 `ledger.accounts_with_names()` 取账户，去掉 `Equity:` 开头的，然后传进去
- [x] 同步修改 `tests/test_graph.py`（两处）和 `tests/test_budget.py` 中 `FixtureModel.query` 的签名
- [x] 测试：fixture 断言 `query()` 收到的账户里有 `("Expenses:Food:Dining", "餐饮")`，并且没有 `Equity:` 开头的账户
- [x] `pytest` 通过
- [ ] 手工验证：用真实模型问「这个月餐饮花了多少」，`account_prefix` 填的是 `Expenses:Food:Dining`，并且能查到记录

## 实现与验证

- 查询协议、真实模型提示词与所有 fixture 同步传入账户和显示名；图层测试断言餐饮真实路径存在且 Equity 不进入提示词。真实 LLM 手工验证未执行，本次使用 FixtureModel 验证。
- 验证：全量 pytest 165 项通过；mypy 36 个源文件通过；npm run build 通过。
