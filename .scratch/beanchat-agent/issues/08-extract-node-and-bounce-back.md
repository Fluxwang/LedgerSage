# 08 · Extract 节点、校验规则与打回回边

Status: open
Milestone: M1
Blocked by: 06, 07

## 背景

Extract 阶段如果发现句式不像完整的新交易描述，应打回重新分类，而不是硬造一笔分录。见 ADR-0001。

## 要做什么

- `services/agent/nodes/extract.py`：输入消息 + 该用户账户列表（**带显示名**）+ 向量召回的相似历史交易；输出交易**数组**（支持多笔，ADR-0010）。
- 每笔字段：`amount`、`date`（绝对 ISO 日期）、`payee`、`narration`、`from_account`、`to_account`、`tags`。记账**只收绝对日期**——「上个月」这类模糊日期在记账语境下直接触发打回。
- **打回规则用确定性代码实现**（不是 LLM 自评），命中任一条即带理由回到 Classify：
  - 缺明确金额主体
  - 日期是范围而非具体某天
  - 句中含疑问词（吗 / 呢 / 为什么 / 多少 / 几 / 是不是）
  - 商户字段是品类词而非具体商家
- 图状态里记 `bounce_count`；**打回最多一次**，第二次直接转 Ask，不再赌。

## 完成标准

- 单测：`我上个月为什么订阅花了150元` 若被 Classify 误判为 record，Extract 必须打回，且打回理由包含「含疑问词」和「日期是范围」。
- 单测：连续两次打回不会发生——第二次进入 Ask 分支。
- 单测：`早饭12 打车32 咖啡28` 抽出三笔。

## 注意

`services/parser.py`（shlex）与 `vector_service.modify_args_via_vector` 在本票之后即成为死代码，但**先不删**——统一在票 22 清理，避免中途破坏还能跑的旧路径。
