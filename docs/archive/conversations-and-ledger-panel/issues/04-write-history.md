# 04 — 写入历史

**What to build:** 新增 `GET /ledger/history`，返回 LedgerSage 最近替用户做过的写入（记账、设预算、删除），按时间倒序排列。每一条带一句后端生成的摘要，并标出是否已经被撤销。右栏 Ledger tab 里把「写入历史」的占位卡片换成只读列表，**不放撤销按钮**。

详见 spec 的「写入历史」一节，以及 `CONTEXT.md` 的「写入历史」词条。

**Blocked by:** None — can start immediately

**Status:** done

- [x] `Settings` 新增 `ledger_history_limit`，默认值 10
- [x] 只列出提交信息以 `LedgerSage:` 或 `BeanChat:` 开头、动作是 record、set budget 或 delete 的提交；`initialize ledger`、用户的手工提交、undo 提交本身都不出现
- [x] 解析 `undo <sha12>` 提交，给被撤销的那一条填上 `undone_at`
- [x] 每一条的 `summary` 由后端根据 diff 生成：记账是「第一笔的头行」，多笔时加「等 N 笔」；删除是「被删交易的头行」；预算是「显示名 预算 → 金额」
- [x] 返回 `[{ commit, kind, summary, file, committed_at, undone_at }]`，最多 limit 条；只读，不拿写锁
- [x] 前端：在 `api.ts` 里新增 `ledgerHistory()`；卡片放在预算进度下面；已撤销的条目变灰，并显示「已撤销 · 相对时间」；空状态显示「还没有 LedgerSage 写入」；接口失败时只有这张卡片报错
- [x] 刷新时机：页面加载时、确认写入之后、顶栏健康度刷新时；不轮询
- [x] 删除 `LedgerPanel` 里 `GET /ledger/history` 的 `<Stub>`
- [x] 测试覆盖：三种写入都会出现，而且是倒序；撤销后对应条目带 `undone_at`；手工提交不出现；`BeanChat:` 前缀的提交会出现；超出 limit 时截断；摘要格式正确
- [x] `pytest` 和 `npm run build` 都通过
- [x] 手工验证：记一笔、确认后写入历史马上多出一条；到统计页删掉这笔再撤销，回到对话页后，删除那条标为「已撤销」

## 实现与验证

- 新增鉴权的账本级历史接口，支持 LedgerSage / BeanChat 记账、预算、删除与 undo 标记，摘要由 Git diff 生成。显式使用 UTF-8 读取中文提交。浏览器验证确认后刷新、统计页删除与撤销后返回刷新、历史接口失败只影响历史卡片。
- 验证：全量 pytest 165 项通过；mypy 36 个源文件通过；npm run build 通过。
