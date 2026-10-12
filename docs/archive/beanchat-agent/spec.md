# BeanChat：对话式记账 Agent

Status: open

把 BeanBot 从「单用户 Telegram 记账机器人」改造成「多用户 Web 对话式记账系统」：FastAPI + LangGraph 后端、React + Vite 前端，Agent 通过工具调用完成记账与查询，账本文件仍是账务数据的唯一真源。

术语一律以 [`CONTEXT.md`](../../CONTEXT.md) 为准；架构决策见 [`docs/adr/`](../../docs/adr/)，本文不重复论证，只引用。

## 目标

1. 用户在对话框里说人话，Agent 判断这是**记账**还是**查询**，并在信息不足时**停下来追问**而不是猜。
2. Agent 的每一步推理实时呈现在决策面板上，并留痕可回放。
3. 账本文件的写入是安全的：纯追加、串行、每次写入一个 git commit、可撤销。

## 非目标

- **amend（修改历史 / 改分类规则）不在本期范围**。仓库目前只有 append 能力，改写需要定位、重写、备份、回滚一整套原语。设计稿 `RUNS` 里的 `#1474` 本期是纯 mock。
- 不做横向扩展。ADR-0002 已将服务钉死在单进程单 worker。
- 不做 refresh token、邮箱验证、密码找回。
- 不做移动端原生适配（设计稿本身是 `min-width:1060px` 的桌面布局）。

## 用户与鉴权

- 多用户，每人一本账本，账本是隔离的唯一维度（ADR-0005）。
- 注册需邀请码；JWT HS256，有效期 7 天，无 refresh；密码 bcrypt cost 12；token 存前端 `localStorage`。
- 新用户按模板生成账本目录并 `git init`；也支持在用户记录上指定已存在的账本根路径接管存量账本。

## 对话处理流程

一条用户消息 = 一次**运行（Run）**。图的形状：

```
                  ┌──────────────┐
   user message → │   Classify   │ ← ─ ─ ─ 打回（最多一次）
                  └──────┬───────┘         │
        record ┌─────────┼─────────┐ query │
               ↓         ↓         ↓       │
          ┌─────────┐ ┌──────┐ ┌───────┐   │
          │ Extract │ │Budget│ │ Query │   │
          └────┬────┘ └──┬───┘ └───┬───┘   │
               │ 不像新交易 ─ ─ ─ ─ ─ ─ ─ ─ ┘
               │
      置信度不足 ↓          other / 歧义
          ┌──────────┐ ←─────────────────┐
          │   Ask    │ interrupt() 挂起   │
          └────┬─────┘                   │
               ↓ 用户回复后恢复            │
          ┌──────────┐                   │
          │  Tools   │ insert_transaction / query_* / set_budget
          └────┬─────┘
               ↓
          ┌──────────┐
          │  Reply   │
          └──────────┘
```

### Classify

- 输入：原始消息 + 最近若干轮对话。**不看账户表、不碰账本。**
- 输出：`intent` ∈ {`record`, `query`, `budget`, `other`} + LLM 自报 `confidence`。
- prompt 是**静态 few-shot**，与用户/账本无关（ADR-0001），必须包含「金额 + 疑问词」负例：
  - `我上个月为什么订阅花了150元` → query
  - `上次那顿火锅是不是花了128` → query
  - `这个月餐饮超过500了吗` → query
  - `打车32` → record
- `confidence < 0.6` → 转 Ask。
- 记账与查询混在一条消息里（`早饭12，对了这个月餐饮多少钱`）→ 判 `other`，追问让用户拆开（ADR-0010）。

### Extract

- 输入：消息 + 该用户的账户列表（**带 `name:` 显示名**，ADR-0009）+ 向量召回的相似历史交易。
- 输出：交易**数组**（支持多笔），每笔含 `amount`、`date`（绝对 ISO 日期）、`payee`、`narration`、`from_account`、`to_account`、`tags`。
- **打回规则（确定性代码，非 LLM 自评）**——命中任一条即带理由打回 Classify：
  - 缺明确金额主体
  - 日期是范围而非具体某天
  - 句中含疑问词（吗 / 呢 / 为什么 / 多少 / 几 / 是不是）
  - 商户字段是品类词而非具体商家
- 打回**最多一次**；第二次直接转 Ask。

### 置信度与追问

- 账户与分类置信度 = 该商户/品类历史交易中最高频账户的占比，阈值 **0.70**（ADR-0004）。
- 无历史 → 一律追问。
- 追问通过 LangGraph `interrupt()` 挂起，状态存 SQLite checkpointer；用户下条消息带同一 `thread_id` 恢复（ADR-0007）。挂起 24 小时未回复即作废。
- 追问是正常终态，不是失败。

### 写入

- 多笔整批原子：任一笔缺信息则整批挂起补齐，齐备后一次性写入、打成**一个** git commit；撤销整批撤（ADR-0010）。
- 纯 append，per-ledger 进程内锁，无 `bean-format`（ADR-0002）。
- 写入目标文件**每次写入时**按当前日期计算，修掉现有的跨月不切文件缺陷。

## 查询

固定参数化工具，BQL 由代码拼装，LLM 只填参数（ADR-0006）：

| 工具 | 参数 |
|---|---|
| `query_transactions` | `start`, `end`, `account_prefix`, `payee`, `min_amount`, `max_amount`, `group_by`, `limit` |
| `get_balance` | `account_prefix`, `as_of` |
| `list_accounts` | `prefix` |

时间字段：枚举优先（`this_month` / `last_month` / `this_week` / `last_n_days:N` / `this_year`）由 `dateutil` 计算；表达不了时才允许 ISO 区间，代码校验 `start <= end`、不在未来、跨度 ≤ 5 年。

## 预算

`custom "budget"` 指令，追加式，独立 `budgets.bean`（ADR-0008）。

## 运行轨迹

- `runs`：一次运行的元信息（用户、thread、意图、耗时、token、状态）。
- `run_steps`：有序步骤（kicker、标题、耗时、payload），对应设计稿决策面板的每一格。
- 传输：SSE 流式，前端用 `fetch` + `ReadableStream` 手工读流（`EventSource` 带不了 `Authorization` header）。
- checkpoint 只管续跑，**不用于展示**。

## 前端

以 `frontend/index.html` 为视觉与信息架构的基准，三个视图全部接真实后端：

- **对话**：消息流 + 回执卡片（含撤销）+ 快捷回复按钮 + 右侧实时决策面板。
- **仪表盘**：账户卡片、月度趋势、分类支出、最近记账。走**专用 REST 端点**，不经过 Agent。
- **决策历史**：`runs` 分页列表 + 详情时间线，支持按 `有追问 / 记账 / 查询` 过滤。

配色、字体、间距沿用设计稿的 CSS 变量体系（含深浅色主题）。

## 部署

单镜像多阶段构建（node 构建前端 → python 运行），`docker compose` 一个服务 + 两个卷（`ledgers/`、`data/`）。镜像需含 `git`。配置全部走环境变量（ADR-0011）。

## 已知风险（未解决，需后续决策）

- **账本卷的备份**：容器化后 `ledgers/` 是唯一真源，本地 git 与卷同生共死，需要定期外传机制。
- **LLM 成本无上限**：目前没有任何限流，单用户误操作可刷爆额度。
- **amend 缺位**：用户记错了只能撤销重记，不能改。

## 里程碑

- **M1 垂直切片**（票 01–15）：登录 → 说一句话 → 分类 → 抽取 → 追问 → 写账本 → git commit → SSE 面板。查询、仪表盘、预算全空。
- **M2 查询**（票 16–18）：查询工具集、query 链路、仪表盘。
- **M3 补齐与收尾**（票 19–22）：预算、决策历史页、向量库增量、部署与旧代码清理。
