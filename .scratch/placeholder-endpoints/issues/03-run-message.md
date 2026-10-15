# 03 — 运行保存用户原话

**What to build:** 每次**运行**都记下触发它的那句完整的用户原话。现在用户原话没有存进数据库：运行的 `title` 在结束后会被改写成「查询账本」这样的摘要，`PARSE` 步骤也只有记账分支才会写。用户在决策历史详情里能看到这次运行是由哪句话触发的。常用查询（04）和历史对话回放（05）都依赖这句原话。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 新增一个版本迁移，给 `runs` 表加 `message` 列；已有的数据库能直接升级，旧运行的 `message` 为空
- [ ] 创建运行时写入完整的用户原话，不截断；追问恢复时不新建运行，也不覆盖原来的 `message`
- [ ] `GET /runs/{id}` 和 `GET /runs` 的每一行都返回 `message`
- [ ] 决策历史详情页顶部显示原话；旧运行的 `message` 为空时，退回显示 `title`
- [ ] 测试：用 `converse()` 发一句超过 60 个字的话，`/runs/{id}` 返回的 `message` 是完整原文；一次带追问的运行在答复后，`message` 仍然是第一句话；迁移测试覆盖从旧版本升级的情况
- [ ] `npm run build` 通过
