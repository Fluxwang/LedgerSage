# 追问用 LangGraph 的 checkpointer + interrupt 实现

追问是一个会跨越多条用户消息的挂起状态：Agent 问「这笔走哪个账户」，用户回一个「微信」——这两个字单独看既不是记账也不是查询，只有在挂起的上下文里才有意义。我们让图在 ASK 节点 `interrupt()` 挂起，状态存进 SQLite checkpointer；用户下一条消息带同一个 `thread_id` 进来，从挂起点恢复执行而不是从头重跑。

## Consequences

- 这是本项目使用 LangGraph 而非普通函数编排的主要理由。若不用这个能力，LangGraph 就是多余的依赖。
- LangGraph 自建的 checkpoint 表会与自有的 `users` / `sessions` / `runs` / `run_steps` 表共存于同一个 SQLite，schema 不由我们控制。
- checkpoint 只负责「能不能续跑」，**不用于展示**。决策面板与决策历史读的是自有的 `run_steps` 表——checkpoint 是序列化的内部图状态，拿去渲染会很难受。
- 挂起状态需要过期策略：24 小时未回复即作废，恢复时若已超时按新会话处理。否则用户问完不答就走，thread 会永远挂在库里。
- 一个「运行」可以跨越多条用户消息（被追问打断再恢复的部分属于同一次运行）。
