# 07 · Classify 节点与 few-shot 负例集

Status: open
Milestone: M1
Blocked by: 01

## 背景

不能靠「有没有金额数字」判断记账 vs 查询——「我上个月为什么订阅花了150元」带金额但是提问。见 ADR-0001。

## 要做什么

- `services/agent/nodes/classify.py`：输入原始消息 + 最近若干轮对话，输出 `intent` ∈ {`record`,`query`,`budget`,`other`} + LLM 自报 `confidence`（Pydantic 结构化输出）。
- **prompt 必须是静态的**：不注入账户列表、不注入账本内容、不注入用户信息。任何动态内容都只允许出现在 Extract（否则 prompt cache 全废）。
- few-shot 例子集单独成文件，重点覆盖「金额 + 疑问词」负例：
  - `我上个月为什么订阅花了150元` → query
  - `上次那顿火锅是不是花了128` → query
  - `这个月餐饮超过500了吗` → query
  - `打车32` / `星巴克38 微信` → record
  - `早饭12，对了这个月餐饮多少钱` → other（记账与查询混合，ADR-0010）
- `confidence < 0.6` → 路由到 Ask。
- 接入 `langchain-openai` 的 `ChatOpenAI`，`base_url` 指向 gpt-5.6-terra 的 OpenAI 兼容端点。

## 完成标准

- 单测：给定固定的 LLM 响应 fixture，路由走向正确（四个意图 + 低置信度共五条分支）。
- 节点输出被写成一条 `CLASSIFY` 的 `run_step`。

## 注意

LLM 自报的 confidence **未经校准**，只用于「很确定 / 完全不确定」的粗筛，不要在它上面设 0.7 这种细阈值（细阈值只作用在账户频次上，见票 09）。
