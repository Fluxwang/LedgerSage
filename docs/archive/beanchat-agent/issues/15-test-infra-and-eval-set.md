# 15 · 测试基建与分类评测集

Status: open
Milestone: M1
Blocked by: 05, 08

## 背景

仓库目前零测试基础设施。`beanbot/test/*` 是被 gitignore 的私人草稿区，不是测试套件。这次改造动的恰恰是会毁数据的路径。

## 要做什么

三档测试，放在顶层 `tests/`：

1. **纯函数单测**：BQL 拼装、频次置信度、Extract 的打回规则、`custom "budget"` 解析、时间枚举归一。
2. **Gateway 集成测**：`tmp_path` 造最小账本 + `git init`，真跑写入 / 并发 / 撤销 / 跨月（票 05 的完成标准即这一档）。
3. **图分支测**：LLM 用固定 fixture 响应，只验证「给定这个输出，图往哪走」——打回、追问、写入三条分支。

外加一件**不进 CI** 的东西：

4. **分类评测集**：约 30 条句子（重点是「金额 + 疑问词」负例），跑真实 LLM 统计准确率，作为改 few-shot prompt 时的手动回归工具。

## 完成标准

- `pytest` 一条命令跑完 1–3 档，不需要任何 API key。
- 评测集有独立入口（`python -m tests.eval.classify`）和可读的准确率报表。
- `requirements-dev.txt` 含 `pytest`、`pytest-asyncio`。

## 注意

第 4 档没有的话，调 prompt 就是盲改——改好一类、悄悄搞坏另一类，你不会知道。
