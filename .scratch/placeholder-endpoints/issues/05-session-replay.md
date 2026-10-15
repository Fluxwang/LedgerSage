# 05 — 历史对话：列表与回放

**What to build:** 左栏「历史对话」列出用户最近的会话，标题是每个会话第一句话的开头。点开一个会话后，按时间顺序重建每一轮：用户气泡、工具轨迹、回复、结果卡，和当时实时看到的一致。之后发的新消息继续使用这个 `thread_id`。这一张里，待确认写入和追问一律显示为只读的状态（「待确认」「已确认」「追问中」等），能不能继续操作留给 06。

回放的单位是**运行**，不是消息。LangGraph 的 checkpoint 按运行隔离，所以回放只读 `runs` 和 `run_steps`，再加上关联的待确认写入，不读 checkpoint。

**Blocked by:** 03 — 运行保存用户原话

**Status:** ready-for-agent

- [ ] 会话第一次创建运行时，把会话 `title` 写成用户消息的前 20 个字；已有的「新对话」不回填
- [ ] `GET /sessions` 返回 `[{ thread_id, title, last_active_at, has_pending_ask }]`，按 `last_active_at` 倒序，最多 30 条，只包含当前用户的会话
- [ ] `GET /sessions/{thread_id}/runs` 返回按时间升序的运行；每次运行带上 `message`、完整的步骤、关联的待确认写入（带当前 `status`），以及会话级的 `active_run_id` / `pending_at`；这个端点取代前端预设的 `/sessions/{thread_id}/messages`
- [ ] 别人的 `thread_id` 或者不存在的 `thread_id` 返回 404
- [ ] 左栏是真实列表，当前会话高亮；点「＋ 新对话」后，在发出第一条消息之前，列表里不会多出空会话
- [ ] 点开会话后，用回放数据重建对话轮次，复用现有的结果卡、确认卡和工具轨迹组件；`message` 为空的旧运行，用户气泡退回显示 `title`
- [ ] 在回放出来的会话里继续发消息，新运行出现在同一个会话下面
- [ ] 测试：用 `converse()` 在同一个 `thread_id` 下发两句话，`/sessions` 的标题是第一句的开头，`/sessions/{id}/runs` 有两次运行且步骤完整；跨用户隔离；`npm run build` 通过
- [ ] 手工验证：发两条消息、刷新页面，从左栏点回这个会话，能看到两轮完整的对话
