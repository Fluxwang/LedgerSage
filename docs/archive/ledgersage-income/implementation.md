# Implementation verification

Review baseline: `abb6250073b5f086a97150fdf7458e0da406cb1f`.

Tickets 02–10 are implemented. Ticket 01's migration tooling is implemented and rehearsed; applying it to the live ledger awaits approval of the 12 names in `account-names.json` and resolution of the existing dirty ledger worktree.

The current ledger has 138 accounts, rather than the spec's historical count of 106. On an isolated copy of the current working ledger, migration named all 138 accounts, preserved the account count, loaded with zero errors, and produced a separate migration commit. The live ledger was not changed.

Backend verification uses the agreed seams: conversation event streams with a fixed-response model, pending-write service, ledger values, confidence candidates, and migration. Covered behaviors include salary signs, reversed accounts, transfers, credit-card repayment, dual autofill, explicit-account precedence, candidate limits, ambiguity, unsupported split salaries, edited confirmation, batch isolation, expiry, and rollback.

The browser walkthrough used a temporary SQLite database and ledger, with fixed salary extraction: salary history autofilled WeChat; the confirmation card changed the destination to Alipay; the preview refreshed; confirmation persisted Income -5000 / Alipay +5000. No real LLM or live financial data was written.

A pre-existing write-destination mismatch was fixed because it prevented this verification: freshly scaffolded ledgers include `20*/*.bean`, while writes previously went into `20*/0-default/`. Writes now use the existing nested layout when present, otherwise the scaffold's direct year directory.

Live migration command, after approval and a clean worktree:

```sh
.venv/bin/python -m beanbot migrate-account-names Beancount --names docs/archive/ledgersage-income/account-names.json --apply
```

## 两轴评审与收尾（2026-09-19）

标准轴与 spec 轴各跑一遍，两轴都确认代码本身没有偏离；被指出来的是**文档**与代码脱节，以及一个用户可见的标题缺口：

- `run_title` 写死「记录{payee}支出」，收入与转账的运行在历史列表里都被叫作支出。抽出共享的 `flow_direction()`（`TransactionInput.direction` 改为委托给它），标题按方向生成，两个账户没填齐时退回「交易」。先写失败测试再修。
- 方向的取值收成 `Literal`，空账户名在构造期被挡掉，`or '转账'` 这条兜底从此真的到不了。
- ADR 0014、CONTEXT.md、spec 与票 04 原本都写着「支出账户落在流出侧也自动换位」，而 `2d837b2` 为保住退款形态（支出账户记负数、资金账户记正数）刻意不换位。四处文档统一补上这个例外——代码是对的，换位会把一笔退款写成一笔支出。

最终结果：`pytest` 100 passed，`mypy beanbot` 干净，`npm run build` 通过。

## 票 01 线上迁移已执行（2026-09-19）

用户确认了 12 个人工拟名，并要求丢弃 `accounts/assets.bean` 上那 6 行仅行尾符（CRLF）的改动。丢弃后工作区干净，先跑预览（106 行，逐条核对过 12 个人工名），再执行：

```sh
.venv/bin/python -m beanbot migrate-account-names data/ledgers/d2e206403a0f438699d2d2153d218729 \
  --names docs/archive/ledgersage-income/account-names.json --apply
```

结果：账本加载 0 错误，账户总数仍是 106，交易 1234 笔不变，**106 个账户全部带上 `name:` meta**（此前是 0 个）。被整行注释掉的 `open` 行（如 `; open Assets:Cash HKD`）没有被碰。改动在账本仓库中单独成一次提交 `615f5a4`，迁移后工作区干净。

拿真账本验过追问候选：收入场景给出的是「银行-01 / 微信余额 / 余额 / 银行-04 / 人民币现金」，支出场景给出「…/ 花呗」，全部显示中文名，没有一个退回英文账户路径，权益账户不出现在候选里。

**一处可选的后续**：`Assets:Alipay:Balance` 的显示名是「余额」——直接取自账本里的行尾注释。它和「微信余额」并排出现在候选按钮上时不好区分，建议改成「支付宝余额」。这是账本原文里的用词，没有替你改。