# 13 · React + Vite 骨架、登录页与对话页

Status: open
Milestone: M1
Blocked by: 03

## 背景

`frontend/index.html` 是 Claude Design 出的静态设计稿，数据全是写死的演示数据。本票把它的视觉语言迁进真正的 React 应用。

## 要做什么

- `web/` 下建 Vite + React + TypeScript 工程；路由三页（对话 / 仪表盘 / 决策历史），后两页本期占位。
- **把设计稿的 CSS 变量体系整套搬过来**：`--bg` / `--surface` / `--accent` 那套色板、`Cormorant Garamond` + `Lora` + `Noto Serif SC` 字体、以及 `prefers-color-scheme` + `[data-theme]` 的双向主题覆盖写法。
- 登录页（设计稿没有，按同一套视觉自行设计）+ token 存 `localStorage` + 401 自动跳登录。
- 对话页：消息流、用户/Agent 气泡、日期分隔线、composer（`⌘↩` 发送）、快捷回复按钮、分录回执卡片（含撤销/编辑入口）。

## 完成标准

- 登录 → 发消息 → 看到 Agent 回复 → 回执卡片显示真实分录 → 点撤销真的撤销。
- 深浅色主题在系统切换与手动切换下都正确。
- 页面在 1060px 宽度下不横向滚动（与设计稿的 `min-width` 约束一致）。

## 注意

`frontend/index.html` **保留不动**，作为视觉基准；不要在它上面改造。
