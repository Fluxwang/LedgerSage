# 02 — 删除对话

**What to build:** 让「⋯」菜单里的「删除」真正可用。删除是软删除：被删的对话从列表和回放里消失，账本不受任何影响。这个对话里还在 pending 的待确认写入一并标为 `rejected`，因为删掉之后就再也没有地方能点确认了。已经确认的写入留下的审计痕迹，以及从这个对话收藏的常用查询，都保留不动。

详见 spec 的「对话：重命名与删除」，以及 `CONTEXT.md` 的「对话」词条。

**Blocked by:** 01（「⋯」菜单）

**Status:** ready-for-agent

- [ ] 新增迁移 `005_session_deleted_at.sql`，给 `sessions` 表加 `deleted_at TEXT`；这个迁移要能在已有数据库上升级
- [ ] `DELETE /sessions/{thread_id}`：在同一个事务里设置 `deleted_at`，并把这个对话下的 pending 写入全部改为 `rejected`；成功返回 204；别人的、不存在的、已删除的对话返回 404
- [ ] `GET /sessions` 过滤掉已删除的对话；`GET /sessions/{thread_id}/runs` 遇到已删除的对话返回 404；`PATCH` 遇到已删除的对话也返回 404
- [ ] `GET /sessions` 的每一项增加 `pending_write_count`：没过期、仍是 pending 的待确认写入笔数
- [ ] `/chat/stream` 收到已删除对话的 `thread_id` 时返回 404，不会让对话复活
- [ ] 不删除 runs、run_steps、pending_writes、saved_queries，也不删除 checkpoint
- [ ] 前端：删除前先弹确认框，文案是「删除对话「xxx」？账本不受影响。」；`pending_write_count > 0` 时补一句「其中 N 笔待确认的记账会一并丢弃。」
- [ ] 删掉当前打开的对话后，切到新对话，行为和点「＋ 新对话」一样
- [ ] 测试覆盖：删除后在列表和回放里都看不到；pending 写入变为 rejected，再 confirm 会被拒绝；常用查询和已确认的记录都还在；`/chat/stream` 返回 404；跨用户返回 404
- [ ] `pytest` 和 `npm run build` 都通过
- [ ] 手工验证：在一个有待确认写入的对话上点删除，确认框里显示笔数；删除后账本文件没有任何变化
