# 01 — 对话列表「⋯」菜单与重命名

**What to build:** 在左栏对话列表的每一项右侧加一个「⋯」，点开后是一个小菜单，里面有「重命名」和「删除」两项（删除的行为在 02 实现，这张票里先放一个禁用的菜单项）。点「重命名」后，标题原地变成输入框，Enter 保存，Esc 或失焦取消。后端新增 `PATCH /sessions/{thread_id}`。另外把自动标题的截取长度从 20 改成可配置，默认 10 个字。

详见 spec 的「对话：重命名与删除」和「配置」两节。

**Blocked by:** None — can start immediately

**Status:** done

- [x] `Settings` 新增 `conversation_title_max_length`（默认 40）和 `conversation_title_auto_length`（默认 10）
- [x] `database.session()` 生成自动标题时改用 `conversation_title_auto_length`；已经存在的旧标题不回填
- [x] `PATCH /sessions/{thread_id}`：保存前去掉首尾空白；空串或超过上限返回 422；别人的或不存在的对话返回 404；成功时返回 `{ thread_id, title }`
- [x] 改名后再在这个对话里发消息，标题保持不变
- [x] 「⋯」在鼠标悬停或选中时显示；「本次对话」（还没落库）不显示「⋯」；当前对话在 `running` 时，「⋯」不能点
- [x] 重命名在原位置编辑，不弹窗；422 时显示后端返回的文案，原标题不变
- [x] 测试覆盖：去空白、422、跨用户 404、改名后列表能看到新标题、发消息后标题不被覆盖、自动标题截取到配置的长度
- [x] `pytest` 和 `npm run build` 都通过
- [x] 手工验证：改名、按 Esc 取消、清空后保存失败

## Comments

- 已完成：新增可配置的重命名上限（默认 40）和自动标题长度（默认 10），已有标题不回填；PATCH 去除首尾空白，校验失败返回中文 422，用户隔离与已删除对话返回 404。
- 左栏新增「⋯」菜单，支持原地编辑、Enter 保存、Esc / 失焦取消；运行中的当前对话不能操作，尚未落库的「本次对话」不显示菜单。422 时显示后端文案并保留原标题。
- 浏览器验证通过：空标题、超长标题、去空白保存、Esc / 失焦取消、继续发送后标题保持、运行中禁用菜单和刷新后持久化。
- 验证：全量 pytest 128 项通过；mypy 34 个源文件通过；`npm run build` 通过。原有自动标题测试按新默认长度更新为 10。
- 本分支原有 npm 锁文件未包含已声明的 code-inspector-plugin，`npm ci` 无法直接使用；本地通过 `npm install --no-package-lock --ignore-scripts --no-audit --no-fund` 补齐依赖后完成构建，未修改依赖声明或锁文件。
