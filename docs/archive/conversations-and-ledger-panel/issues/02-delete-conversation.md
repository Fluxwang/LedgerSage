# 02 — 删除对话

**What to build:** 让「⋯」菜单里的「删除」真正可用。删除是软删除：被删的对话从列表和回放里消失，账本不受任何影响。这个对话里还在 pending 的待确认写入一并标为 `rejected`，因为删掉之后就再也没有地方能点确认了。已经确认的写入留下的审计痕迹，以及从这个对话收藏的常用查询，都保留不动。

详见 spec 的「对话：重命名与删除」，以及 `CONTEXT.md` 的「对话」词条。

**Blocked by:** 01（「⋯」菜单）

**Status:** done

- [x] 新增迁移 `005_session_deleted_at.sql`，给 `sessions` 表加 `deleted_at TEXT`；这个迁移要能在已有数据库上升级
- [x] `DELETE /sessions/{thread_id}`：在同一个事务里设置 `deleted_at`，并把这个对话下的 pending 写入全部改为 `rejected`；成功返回 204；别人的、不存在的、已删除的对话返回 404
- [x] `GET /sessions` 过滤掉已删除的对话；`GET /sessions/{thread_id}/runs` 遇到已删除的对话返回 404；`PATCH` 遇到已删除的对话也返回 404
- [x] `GET /sessions` 的每一项增加 `pending_write_count`：没过期、仍是 pending 的待确认写入笔数
- [x] `/chat/stream` 收到已删除对话的 `thread_id` 时返回 404，不会让对话复活
- [x] 不删除 runs、run_steps、pending_writes、saved_queries，也不删除 checkpoint
- [x] 前端：删除前先弹确认框，文案是「删除对话「xxx」？账本不受影响。」；`pending_write_count > 0` 时补一句「其中 N 笔待确认的记账会一并丢弃。」
- [x] 删掉当前打开的对话后，切到新对话，行为和点「＋ 新对话」一样
- [x] 测试覆盖：删除后在列表和回放里都看不到；pending 写入变为 rejected，再 confirm 会被拒绝；常用查询和已确认的记录都还在；`/chat/stream` 返回 404；跨用户返回 404
- [x] `pytest` 和 `npm run build` 都通过
- [x] 手工验证：在一个有待确认写入的对话上点删除，确认框里显示笔数；删除后账本文件没有任何变化

## Comments

- 已完成：迁移 005 新增 deleted_at；软删除与全部 pending 写入（含超时但未转终态的记录）改为 rejected 在同一事务里完成，成功返回空体 204。
- 列表与回放过滤已删除对话，PATCH / DELETE / chat stream 拒绝已删除对话；在建立 SSE 响应前返回真正的 HTTP 404，存储层也拒绝复用已删除的 thread_id。
- 列表新增未过期 pending_write_count；前端弹框前重新读取笔数，删除确认包含账本不受影响及丢弃笔数提示；取消不删除，删除当前对话复用「＋ 新对话」的重置逻辑。
- HTTP 测试验证账本原文、已确认写入、常用查询、运行、步骤和 checkpoint 全部保留；覆盖跨用户隔离、迁移升级及重复启动、追问不可恢复、删除后 confirm 被拒绝，以及更新失败时事务整体回滚。
- 浏览器验证通过：含 1 笔待确认写入的删除确认、取消删除、确认删除后切到新对话、账本文件不变，以及刷新后对话仍不可见。
- 验证：全量 pytest 128 项通过；mypy 通过；`npm run build` 通过。
