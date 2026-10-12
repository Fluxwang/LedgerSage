# 09 · 账户置信度（历史频次）与向量召回上下文

Status: open
Milestone: M1
Blocked by: 08

## 背景

置信度必须有可计算、可复现、可单测的定义。账户置信度 = 该商户/品类的历史交易中最高频账户的占比（火锅 8 次里 6 次微信 → 0.75），阈值 0.70。见 ADR-0004。

设计稿 `frontend/index.html:406` 里「历史 6/8 却给出 account confidence 0.41」的数字是画稿占位，不自洽，不作为实现依据。

## 要做什么

- `services/agent/confidence.py`：给定 payee/品类，从账本历史统计各账户出现频次，返回 `[(account, count, ratio)]`。
- 阈值判定：最高 `ratio < 0.70` 或无历史 → 该字段置信度不足 → 转 Ask。
- 向量召回改为**只提供 few-shot 上下文**（相似历史交易原文），不再改写参数生成候选。
- 把频次证据写进 `run_step` 的 payload，供决策面板展示证据链（设计稿 `query_accounts()` 那一格）。

## 完成标准

- 单测：构造 8 笔火锅历史（6 微信 / 2 信用卡），`ratio` 为 0.75，判定为通过阈值。
- 单测：全新商户无历史 → 转 Ask。
- 面板 payload 里能看到 `Assets:WeChat:Balance 6/8` 这样的证据。

## 注意

冷启动阶段追问会偏频繁，这是刻意接受的代价——第一次买东西就该问清楚走哪个账户。
