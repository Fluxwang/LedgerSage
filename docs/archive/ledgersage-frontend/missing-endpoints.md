# LedgerSage 前端：缺失接口清单

设计稿 `LedgerSage.dc.html` 的前端已经按稿实现（`web/src/`）。本文列出它需要、但后端现在没有的端点。

**读法**：前端里凡是走 `web/src/api.ts` 的 `pending()` 的函数，都会抛 `MissingEndpoint`，界面渲染成一张写着端点名的「待接口」占位卡，而不是假数据。所以这张表和界面上的占位卡是一一对应的——补完一个端点，就把 `api.ts` 里对应的 `pending()` 换成真的 `api()` 调用，界面自动活过来。

已经在用的端点：`/auth/register`、`/auth/login`、`/auth/me`、`/chat/stream`、`/dashboard`、`/accounts`、`/transactions`、`/transactions/{id}/raw`、`DELETE /transactions/{id}`、`/transactions/{commit}/undo`、`/chat/pending/{id}/confirm`、`/chat/pending/{id}/reject`、`/runs`、`/runs/{id}`、`/admin/vector/*`。

编号保持原样，做掉的条目从下面移走了，剩下的还按旧号称呼（P0-1、P1-7……），免得引用失效。

## 已经做掉的

| | 端点 | 决策 |
|---|---|---|
| 原 P0-3 | `GET /transactions`、`GET /transactions/{id}/raw` | 交易 id 是 `base64url("<相对路径>:<行号>:<摘要>")`，摘要用来挡住「账本变了还照着旧 id 删」。**id 只在某个账本版本内有效**，前端每次增删后都要重拉。 |
| 原 P1-6 | `receipt` 带 `pending_id` + `POST /chat/pending/{id}/{confirm,reject}` | 两段式写入，见 **ADR 0012**。`tools` 与 `budget` 节点现在只渲染 diff，落盘在确认时发生。`receipt` 的含义因此变了：带 `pending_id` 的是预览，带 `commit` 的是已落盘。 |
| 原 P2-11 | `DELETE /transactions/{id}` | 见 **ADR 0013**。没有走「追加冲正分录」那条路——用户说删除多半是因为这笔根本不该存在，配一笔假退款会污染此后所有按收款方、按分类的统计。撤销复用既有的 `POST /transactions/{commit}/undo`，所以没有新增 undo 端点。 |

顺带解决的：`step` 事件现在每个节点都会发。原先 `tools` 节点只发 `receipt`，时间线上看不到「写入账本」那一步，三层呈现缺了第一层。

---

## P0 · 缺了它设计稿就撑不起来

### 1. `GET /ledger/status`

顶栏的 `~/ledger/2026.beancount`、`bean-check clean`、`1,284 txns · CNY · git 已同步`，以及统计页右栏整张「账本健康度」卡，都指向同一份数据。

```json
{
  "file": "2026/09-expenses.bean",
  "currency": "CNY",
  "transaction_count": 1284,
  "bean_check": { "ok": true, "message": "" },
  "git": { "clean": true, "synced_at": "2026-09-17T16:02:11+08:00" },
  "health": [
    { "level": "warn", "text": "3 笔缺少收款方" },
    { "level": "warn", "text": "2 个账户未对账 > 30 天" }
  ]
}
```

- 前端落点：`main.tsx` 顶栏、`explore/Explore.tsx` 的 `SideRail`、`chat/LedgerPanel.tsx` 的校验区。
- `transaction_count` 目前只能从 `/dashboard` 的 `recent.total` 拿，语义是「全历史笔数」，勉强能用；其余三项无处可取。
- `bean_check` 需要真跑一次校验。如果嫌贵，可以做成「写入时缓存结果、这里只读缓存」。

### 2. `GET /sessions` + `GET /sessions/{thread_id}/messages`

左栏「对话」列表。现在 `thread_id` 是前端 `crypto.randomUUID()` 生成的，刷新即丢，`sessions` 表里躺着的会话没有任何办法列出来或者恢复。

```
GET /sessions?page=1&size=20
→ { "rows": [ { "thread_id": "...", "title": "今天的几笔支出",
                "updated_at": "...", "run_count": 4 } ], "total": 12 }

GET /sessions/{thread_id}/messages
→ [ { "role": "user", "content": "...", "at": "..." },
    { "role": "agent", "content": "...", "run_id": "...", "receipts": [...] } ]
```

- 前端落点：`chat/Chat.tsx` 左栏，以及切换会话后的消息回放。
- 消息回放需要**用户消息也落库**。现在 `runs.title` 存的是截断过的标题，不是原文；`steps` 存了 Agent 那一侧，用户那一侧没有。这是这条里真正的工作量。
- 工具轨迹可以复用 `GET /runs/{id}` 的 `steps`，回放时按 `run_id` 拉即可。

### 4. `GET /statements/income`

收支表。设计稿要的是「账户层级 × 连续多个月」的矩阵，带趋势迷你条和逐行下钻；`/dashboard` 只给单个区间的分类合计，拼不出来。

```
GET /statements/income?start=2026-04&end=2026-09&account=Expenses&tag=
→ { "periods": ["2026-04", ..., "2026-09"],
    "rows": [ { "account": "Expenses", "display_name": "支出", "depth": 0,
                "cells": [ { "period": "2026-04", "amount": "11204.00" }, ... ] } ],
    "totals": { "expense": "72914.00", "income": "126000.00", "net": "53086.00",
                "savings_rate": "0.421",
                "peak": { "period": "2026-08", "amount": "14286.00" } },
    "composition": [ { "period": "2026-04",
                       "parts": [ { "account": "Expenses:Housing",
                                    "display_name": "住房", "amount": "5600.00" } ] } ] }
```

- 前端落点：`explore/Explore.tsx` 的 `IncomeStatement`。现在这一屏用 `monthly_trend` + `categories` 顶着，能看月度总额和本期分类，但没有矩阵、没有堆叠构成、没有储蓄率（收入侧完全没有聚合）。
- **收入侧现在是空白**：`/dashboard` 的 `categories` 只算 `Expenses:`，`accounts` 只出 `Assets:` / `Liabilities:`。`Income:` 在整个 REST 面上没有出口。

### 5. `GET /statements/balance`

资产负债页。

```
GET /statements/balance?as_of=2026-09-17&months=6
→ { "as_of": "...", "currency": "CNY",
    "net_worth": "82194.00", "net_worth_change": "2014.00",
    "assets": "86412.00", "liabilities": "-4218.00", "liquidity_months": "4.5",
    "trend": [ { "period": "2026-04", "net_worth": "53620.00",
                 "liabilities": "-4080.00" } ],
    "rows": [ { "account": "Assets:Bank:CMB:Debit", "display_name": "招行储蓄卡",
                "depth": 1,
                "cells": [ { "period": "2026-07", "amount": "46880.00" } ] } ],
    "allocation": [ { "account": "Assets:Bank:CMB:Debit", "display_name": "招行储蓄卡",
                      "amount": "52180.00", "share": "0.604" } ],
    "reconciliation": [ { "account": "Assets:Fund:Index", "date": "2026-08-01",
                          "amount": "30810.00", "currency": "CNY",
                          "ok": true, "stale_days": 47 } ] }
```

- 前端落点：`explore/Explore.tsx` 的 `BalanceSheet`。当前余额、资产配置环、流动性覆盖已经用 `/dashboard` 算出来了；**缺的是按日期回溯的余额**（净资产走势、07/08 月末两列）和 `balance` 指令的对账状态。
- `Ledger.balances(prefix, as_of)` 已经支持 `as_of`，回溯这部分基本是现成的，包一层就行。
- 对账状态需要读账本里的 `balance` 指令并跟实际余额比对，这块是新的。

---

## P1 · 设计稿的关键交互靠它

### 7. `GET /ledger/raw`

右栏「即将写入的 diff」要显示写入位置**前后**的账本原文（设计稿里 4124–4127 是上下文，4128–4131 才是新增），查询场景的「查询命中的原始条目」也要它。

```
GET /ledger/raw?file=2026/09-expenses.bean&around=4128&context=4
→ { "file": "...", "start_line": 4124, "lines": ["...", "..."] }
```

- 前端落点：`chat/LedgerPanel.tsx` 的 `Diff`。现在只渲染回执里带的那几行新增，没有上下文。
- 只读端点，但要挡住路径穿越：`file` 必须落在该用户账本根目录内。

### 8. `GET /accounts/tree`

统计页左栏账户树。`/accounts` 只返回 `{account, display_name}`，没有层级也没有金额。

```
GET /accounts/tree?start=&end=
→ [ { "account": "Assets", "display_name": "资产", "depth": 0, "amount": "86412.00",
      "children": [ ... ] } ]
```

- 前端落点：`explore/Explore.tsx` 的 `buildTree`。现在是拿 `/dashboard` 的 `accounts` + `categories` 拼的两层假树：只有 Assets / Liabilities / Expenses 三个根，**Income 整个缺席**，深层账户（`Food:Dining`）也没有正确嵌套。

### 9. `GET /analytics/top-payees`

右栏「前十收款方」。

```
GET /analytics/top-payees?start=&end=&limit=10
→ [ { "payee": "链家", "amount": "33600.00", "count": 6 } ]
```

`Ledger.query_transactions(group_by="payee")` 已经能算，缺的只是一个 REST 出口（Agent 工具能调，仪表盘调不到）。

### 10. `GET /ledger/history`

右栏「写入历史」：最近几次写入、增删行数、是否已回滚。

```
GET /ledger/history?limit=10
→ [ { "commit": "8f21a", "at": "2026-09-16T21:04:00+08:00",
      "file": "2026/09-expenses.bean", "added": 4, "removed": 0,
      "reverted": false, "summary": "record 1 transaction(s)" } ]
```

git log 里全都有，包一层即可。

---

## P2 · 锦上添花，可以往后排

### 12. `GET /saved-queries` + `POST /saved-queries`

「常用查询」，以及查询结果卡上的「存为常用」「固定到仪表盘」。要一张新表（非账务数据，归 `storage`）。

### 13. `GET /reports/monthly` + `POST /reports/export`

设计稿第四个场景是月度报表：收入/支出/储蓄率三个 KPI、支出构成前四、净现金流近六月、同比变化，外加「导出 PDF」和「写入 reports/2026-08.md」。

这一整块目前**在 Agent 侧也不存在**——没有 `monthly_report` 工具。要做的话是两件事：一个确定性的 REST 聚合端点（给统计页用），一个 Agent 工具（给对话用）。按 ADR 0006 的说法，聚合查询走专用 REST、不经过 LLM，所以端点是主，工具只是包一层。

导出 PDF 需要新的运行时依赖，建议先只做 Markdown。

### 14. `GET /transactions/export.csv`

查询结果卡和收支表上的「导出 CSV」。注意浏览器下载要带 `Content-Disposition`，鉴权得用 query token 或者先换一次性下载链接（现在是 `Authorization` 头，`<a download>` 带不上）。

### 15. `GET /suggestions`

输入框上方的建议 chips 现在是 `chat/Chat.tsx` 里写死的三条。做成端点的话可以按账本实际情况给（最近的商户、快到期的预算、还没对账的账户）。优先级很低。

### 16. `/chat/stream` 增加 `context` 参数

设计稿里统计页有「在对话里追问这张表」「把这张视图交给 Agent」，并注明「当前筛选条件会作为上下文带进对话」。现在前端只是把问题文本塞进输入框（`main.tsx` 的 `ask()` → `Chat` 的 `seed`），筛选条件丢了。

```json
{ "message": "...", "thread_id": "...",
  "context": { "start": "2026-09-01", "end": "2026-09-30",
               "account": "Expenses:Food", "tag": "social" } }
```

### 17. 主动推送：`GET /events/stream` + 定时任务

设计稿的预算场景是「定时任务 · 每日 21:00 · 由 Agent 主动发起」——不是用户提问，是系统推过来的。现在整条链路只有「用户发消息 → SSE 回」这一个方向。

要做的话需要：一个常驻的定时器（单 worker 的约束下可以就放在进程里）、一条服务端推送通道、以及「Agent 主动发起的 run」在 `runs` 表里怎么归属。工作量不小，建议单开一张票。

前端落点：`chat/Chat.tsx` 的 `Turn.note` 字段已经留好了（渲染成设计稿里那个居中的胶囊提示），只是没人往里写。

---

## 明确不做

- **BQL 查询面板**（设计稿统计页顶栏的第五个 tab）。ADR 0006 已经决定不让 LLM 生成 BQL，也没打算把 BQL 作为用户输入暴露出去——用户手写的 BQL 同样只能靠真跑一遍才知道错在哪，报错还是解析器的内部语法错误。前端里这个 tab 是禁用的，hover 上去写明了原因。
- **持仓 / 多币种**（第四个 tab）。同样禁用，不在当前范围。

---

## 顺带一提：`step` 事件的参数/返回没有分开

设计稿的折叠卡是左右两栏 `arguments` | `result`。现在 SSE 的 `step` 事件只带一个 `payload`（就是该节点的返回 dict），只有 `query` 节点因为 `receipt` 里恰好有 `{tool, arguments, result}` 才凑得出两栏。

前端 `chat/ToolTrace.tsx` 的 `inspect()` 做了兼容：能拆就拆两栏，拆不出就单栏显示整个 payload。如果后端愿意给 `step` 事件补上 `arguments` / `result` 两个字段，这一层兼容就可以删掉，四个场景的折叠卡也就都跟设计稿一致了。

## 另一处：确认之后那句话就过时了

两段式写入落地后，Agent 在预览时说的是「这笔已经准备好，确认后写入账本」。用户点了确认，结果卡翻成「已写入账本」，但上面那句话还留在对话里。

现在的做法是**不改它**——那是 Agent 在那个时刻说的话，对话记录不该被追溯修改。如果读着别扭，正确的解法是确认后再追加一条系统提示（「已写入 2026/09-expenses.bean L33」），而不是把历史消息改掉。这需要一条服务端推送通道，跟 P2-17 是同一件事。
