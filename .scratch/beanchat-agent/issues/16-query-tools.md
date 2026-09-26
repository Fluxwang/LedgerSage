# 16 · 查询工具集与时间表达解析

Status: open
Milestone: M2
Blocked by: 15

## 背景

BQL 是 beanquery 的小众方言，聚合结果是 Inventory 对象——LLM 幻觉率高且错误难以验证与解释。工具签名固定，BQL 由代码拼装。见 ADR-0006。

## 要做什么

三个 LangChain tool：

| 工具 | 参数 |
|---|---|
| `query_transactions` | `start`, `end`, `account_prefix`, `payee`, `min_amount`, `max_amount`, `group_by`, `limit` |
| `get_balance` | `account_prefix`, `as_of` |
| `list_accounts` | `prefix`（返回带显示名） |

时间字段用 Pydantic 联合类型：枚举优先（`this_month` / `last_month` / `this_week` / `last_n_days:N` / `this_year`）由 `dateutil` 计算；表达不了才允许 ISO 区间，代码校验 `start <= end`、不在未来、跨度 ≤ 5 年。

Inventory → 标量的转换收敛到一处，不要再散落 `cell in ("", "()")` 这类判断。

## 完成标准

- 每个工具的 BQL 有对应单测（含空结果、多币种、跨年区间）。
- 时间枚举在跨年边界正确（2026-01-05 问 `last_month` → 2025-12-01..2025-12-31）。
- 现有 `fetch_expense` / `fetch_bill` 保留但**不注册进工具集**（它们是全历史汇总，无时间参数，会答错「这个月花了多少」）。
