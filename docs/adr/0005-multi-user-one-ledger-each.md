# 多用户，每个用户一本独立账本

系统面向多个用户，账本是隔离的唯一维度：一个用户恰好拥有一本账本，账本之间没有任何共享。新用户注册时按模板在 `data/ledgers/<user_id>/` 生成一套可用的账本结构（`main.bean` + 五类账户文件 + 当年目录 + `git init`）；同时允许在用户记录上指定一个已存在的账本根路径，把自托管的存量账本直接接进来。

## Consequences

- 原实现把所有依赖放在模块级全局 `AppContext` 里、靠 `get_context()` 直取——这在 per-user 账本下不成立。`BeancountRepository`、`VectorStore` 及其上的 service 必须改成按 `user_id` 取的带缓存工厂，经 FastAPI `Depends` 注入；只有真正无状态的东西（配置、logger、LLM/embedding 客户端）留在全局。
- 向量库随账本走：`data/ledgers/<user_id>/vector.sqlite`，不再是进程工作目录下的单一 `tx_db.sqlite`。
- 写锁是 per-ledger 的（见 ADR-0002）。
- 模板账本与存量账本的账户命名不一致，Agent 在两者上的行为会有细微差别；模板需要维护一份标准账户表。
- 注册需要邀请码：创建一个用户等于在服务器上创建一个 git 仓库和一个向量库，此后每条消息都消耗 LLM 额度，不能对公网开放。
