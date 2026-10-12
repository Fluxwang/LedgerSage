# 10 · Ask 节点：interrupt 挂起、恢复与过期

Status: open
Milestone: M1
Blocked by: 09

## 背景

用户回的「微信」两个字单独看既不是记账也不是查询，只有在挂起的上下文里才有意义。追问通过 LangGraph `interrupt()` 挂起，状态存 SQLite checkpointer，下条消息带同一 `thread_id` 从挂起点恢复。见 ADR-0007。

## 要做什么

- 接入 LangGraph 的 SQLite checkpointer，与业务表同库（`data/app.sqlite`）。
- `services/agent/nodes/ask.py`：生成追问话术 + **带默认建议的候选列表**（对应设计稿的快捷回复按钮），然后 `interrupt()`。
- 恢复路径：`thread_id` 匹配的下条消息不重新走 Classify，直接从挂起点继续。
- 多笔场景下，挂起状态要记住「数组里第几笔在等哪个字段」（ADR-0010）。
- 过期策略：挂起超过 24 小时作废，恢复时若已超时按新会话处理并告知用户。

## 完成标准

- 端到端：「今天中午和同事吃了火锅，花了128」→ 追问账户 → 回「微信」→ 写入成功，整个过程是**一次运行**（一个 `run` 记录，含 ASK 步骤）。
- 挂起 25 小时后回复 → 不写入，提示会话已过期。
- 用户不回答直接问别的 → 旧 thread 不阻塞新消息。

## 注意

checkpoint 只管「能不能续跑」，**不用于渲染面板**——面板读的是 `run_steps`（票 12）。
