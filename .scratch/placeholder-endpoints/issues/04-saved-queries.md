# 04 — 常用查询

**What to build:** 用户在对话里看到一次查询的回答后，可以点「☆ 存为常用」，把触发这次查询的原话收藏起来。之后在统计页右栏点这一条，就会把这句话作为新消息重新发给 Agent，按当时的账本重新回答。不想要的，鼠标悬停时点 × 删掉。只有意图为 `query` 的运行能被收藏，这条规则由后端校验，因为重放一句记账的话会重复记账（见 CONTEXT.md「常用查询」）。

**Blocked by:** 03 — 运行保存用户原话

**Status:** ready-for-agent

- [ ] 新增一个版本迁移，建 `saved_queries` 表：`id, user_id, question, run_id, created_at`，并对 `(user_id, question)` 加唯一约束
- [ ] `GET /saved-queries` 返回当前用户的 `[{ id, question, created_at }]`，按 `created_at` 倒序
- [ ] `POST /saved-queries` 的请求体是 `{ run_id }`，`question` 取自这次运行的 `message`
- [ ] 对记账运行、预算运行、别人的运行、`message` 为空的旧运行调用 `POST`，都被拒绝，返回 4xx
- [ ] 对同一句话收藏两次，返回同一条记录，列表里只有一条
- [ ] `DELETE /saved-queries/{id}` 只能删除自己的记录；删除别人的或者不存在的记录，都返回 404
- [ ] 查询类回答的结果卡上有「☆ 存为常用」，记账类回答上没有；点过之后显示「已收藏」
- [ ] 右栏列表显示真实数据；点击一条就发起提问；悬停出现 ×，点击后删除并刷新列表
- [ ] 前端的 `SavedQuery` 类型去掉 `params`，`title` 改名为 `question`
- [ ] 测试用按关键词路由意图的 `FixtureModel` 产生查询运行和记账运行，从 HTTP 层断言上面这些行为；`npm run build` 通过
