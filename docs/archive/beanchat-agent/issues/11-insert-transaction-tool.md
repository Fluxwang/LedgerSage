# 11 · `insert_transaction` 工具（整批原子）

Status: open
Milestone: M1
Blocked by: 05, 10

## 背景

LLM 只输出结构化参数，分录文本由代码确定性地生成——不再让模型直接吐 Beancount 文本再反过来 parse 校验。多笔整批原子（ADR-0010）。

## 要做什么

- LangChain tool `insert_transaction`，参数为交易数组，Pydantic 强校验。
- 工具内部：逐笔校验账户真实存在（不存在则报可读的错误，而非写进去）→ 调 `build_transaction_entry` + `render_entry` → 取 per-ledger 锁 → 整批 append → **一个** git commit。
- 返回值含：写入的文件与行号、commit hash（供撤销用）、渲染后的分录文本（供回执卡片展示）。
- 撤销 API `POST /transactions/{commit}/undo`：`git revert` 该 commit 并重载账本。

## 完成标准

- 三笔一次写入 → `git log` 只多一个 commit。
- 其中一笔账户不存在 → 整批不写入，返回明确指出是第几笔的哪个账户。
- 撤销后账本回到写入前状态。
- 回执返回的分录文本与账本文件里的实际内容一致。

## 注意

`ledger_service.generate_transactions` 的 RAG / 向量兜底链在本票之后作废，同样留到票 22 统一清理。
