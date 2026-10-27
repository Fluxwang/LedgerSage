# 查询只暴露固定的参数化工具，不让 LLM 生成 BQL

Agent 的查询能力由一组签名固定、参数受 Pydantic 约束的工具提供（`query_transactions`、`get_balance`、`list_accounts`、`budget_status`），BQL 语句一律由代码拼装。LLM 只填参数，永远不写查询语句。

## Considered Options

**让 LLM 直接生成 BQL** 被否决。BQL 是 beanquery 的小众方言而非 SQL——有 `position`、`cost()`、`convert()` 等自有函数，聚合结果是 Inventory 对象而不是标量（现有 `query_service.translate_rows` 里那句跳过 `"()"` 的判断就是这个类型泄漏出来的痕迹）。模型对它的幻觉率会很高，而错误只能靠真跑一遍才发现，报错还是解析器的内部语法错误，既无法自动修复也无法向用户解释。

## Consequences

- 覆盖面有明确上限：参数表达不了的问题（「周末花的是不是比工作日多」）只能靠拉明细回来自算，或者如实回答做不到。这是刻意接受的边界。
- 每条 BQL 都是自己写的，因而可单测。
- 现有 `fetch_expense` / `fetch_bill` 保留但降级为仪表盘专用：它们没有时间范围参数、算的是全历史汇总，不得进入 Agent 工具集，否则「这个月花了多少」会被答成全历史。
- 仪表盘走专用 REST 端点，不经过 Agent——聚合查询是确定性的，不该花 LLM 的钱，也不该有不确定性。
- 工具集是可以扩的，但每加一个都要在这里记一笔。票 19 加了 `budget_status`（回答「预算还剩多少」，返回按预算自身周期算出的已用 / 上限 / 剩余）——它同样是固定签名、结果由代码算出，没有破坏「LLM 不写查询语句」这条线。
- `query_transactions` 加了 `order_by`（`date` / `amount_desc`），用来回答「最大的一笔开支」「最贵的三笔」。排序和截取都在代码里完成，LLM 只选枚举值，同样没有越过这条线。
