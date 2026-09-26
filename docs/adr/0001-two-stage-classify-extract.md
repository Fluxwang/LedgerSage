# 意图分类与字段抽取拆成两个独立节点

对话入口既要处理记账也要处理查询，而「有没有金额数字」不足以区分两者——"我上个月为什么订阅花了150元"带金额却是查询。我们用一个 LLM few-shot 分类节点（Classify）判定意图，再由独立的抽取节点（Extract）填 `insert_transaction` 的参数，而不是让单次 LLM 调用同时输出意图和字段。

## Considered Options

- **单次结构化输出**（intent + confidence + 字段一起吐）：延迟和 token 减半，但被否决——它无法表达「Extract 发现证据后打回 Classify」这个动作，只能整体重试；且 Classify 的长 few-shot prompt 会被迫每次随动态账户上下文一起重算，prompt cache 全部失效。
- **单 agent 靠 tool choice 隐式分类**：实现最简单，但拿不到显式置信度，做不到置信度兜底与决策面板展示。

## Consequences

- 每笔记账至少两次 LLM 往返。
- Classify 的 prompt 必须保持与用户/账本无关（纯静态 few-shot），否则缓存收益消失；账户列表与向量召回上下文只允许注入 Extract。
- Extract → Classify 的回边最多走一次；第二次直接转「问用户」，避免两个节点互相打回形成死循环。
- **Extract → Classify 的回边只为「这条消息可能不是记账」而存在**，不为「字段没填齐」。两者此前共用一个 `issue` 列表，导致每一次正常追问（缺账户）都白白重跑一轮 Classify + Extract；实测一条工资消息因此多花 8.3 秒，而重跑拿到的必然还是 record。现已拆成两个字段：`issue` 只装抽取质量疑点、负责打回，`missing` 装缺哪条分录行、直接进追问。
- 判定「不像一笔新交易」的是确定性代码规则（缺金额主体 / 日期是范围 / 含疑问词 / 商户是品类词），不是 LLM 自评。
