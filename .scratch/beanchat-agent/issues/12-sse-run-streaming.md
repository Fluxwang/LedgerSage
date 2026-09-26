# 12 · SSE 流式接口与运行轨迹落库

Status: open
Milestone: M1
Blocked by: 02, 11

## 背景

设计稿 `frontend/index.html:433` 那个带脉冲动画、时间显示「运行中」的步骤，是流式才有的画面。

## 要做什么

- `POST /chat/stream`：接收消息，返回 SSE 流。用 LangGraph 的 `astream_events` 采集节点级事件，每个节点结束即推一个 step 事件，同时写 `run_steps`。
- 事件类型：`step`（一格时间线）、`message`（Agent 回复）、`receipt`（分录回执卡片）、`ask`（追问 + 候选按钮）、`done`、`error`。
- `runs` 记录元信息：意图、耗时、token 数、状态（成功 / 有追问 / 失败）。
- **鉴权**：`EventSource` 不支持自定义请求头，因此约定前端用 `fetch` + `ReadableStream` 手工读流，`Authorization: Bearer` 正常带。服务端不接受 query string 里的 token。

## 完成标准

- 一次记账运行推出的 step 序列与设计稿 Run #1482 的形状一致（`PARSE` → `CLASSIFY` → `TOOL` → `ASK` → `TOOL` → `REPLY`）。
- 流中途客户端断开，服务端不泄漏任务、`run` 被标记为中断。
- 运行结束后 `run_steps` 里的记录与流里推过的完全一致（刷新页面能从历史里看到同样的东西）。

## 注意

不要试图用 checkpoint 表渲染面板——那是序列化的内部图状态。
