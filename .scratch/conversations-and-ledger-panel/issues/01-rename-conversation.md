# 01 — 对话列表「⋯」菜单与重命名

**What to build:** 在左栏对话列表的每一项右侧加一个「⋯」，点开后是一个小菜单，里面有「重命名」和「删除」两项（删除的行为在 02 实现，这张票里先放一个禁用的菜单项）。点「重命名」后，标题原地变成输入框，Enter 保存，Esc 或失焦取消。后端新增 `PATCH /sessions/{thread_id}`。另外把自动标题的截取长度从 20 改成可配置，默认 10 个字。

详见 spec 的「对话：重命名与删除」和「配置」两节。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `Settings` 新增 `conversation_title_max_length`（默认 40）和 `conversation_title_auto_length`（默认 10）
- [ ] `database.session()` 生成自动标题时改用 `conversation_title_auto_length`；已经存在的旧标题不回填
- [ ] `PATCH /sessions/{thread_id}`：保存前去掉首尾空白；空串或超过上限返回 422；别人的或不存在的对话返回 404；成功时返回 `{ thread_id, title }`
- [ ] 改名后再在这个对话里发消息，标题保持不变
- [ ] 「⋯」在鼠标悬停或选中时显示；「本次对话」（还没落库）不显示「⋯」；当前对话在 `running` 时，「⋯」不能点
- [ ] 重命名在原位置编辑，不弹窗；422 时显示后端返回的文案，原标题不变
- [ ] 测试覆盖：去空白、422、跨用户 404、改名后列表能看到新标题、发消息后标题不被覆盖、自动标题截取到配置的长度
- [ ] `pytest` 和 `npm run build` 都通过
- [ ] 手工验证：改名、按 Esc 取消、清空后保存失败
