# 03 · 鉴权：邀请码注册、登录、JWT 依赖

Status: open
Milestone: M1
Blocked by: 02

## 背景

创建一个用户等于在服务器上创建一个 git 仓库和一个向量库，此后每条消息消耗 LLM 额度，因此不对公网开放注册（ADR-0005）。

## 要做什么

- `POST /auth/register`：`username` + `password` + `invite_code`；校验邀请码未被使用，创建用户后标记该码已用。
- `POST /auth/login`：返回 JWT。
- `GET /auth/me`：返回当前用户。
- `get_current_user` 依赖：解析 `Authorization: Bearer`，失败返回 401。
- CLI 命令生成邀请码（`python -m beanbot invite --count N`）。

参数：JWT HS256、有效期 7 天、无 refresh token；bcrypt cost factor 12。

## 完成标准

- 无邀请码或邀请码已用 → 400 且不创建任何用户。
- token 过期 → 401（不是 500，也不是 200 加空数据）。
- 密码不以任何形式出现在日志里。

## 注意

前端把 token 存 `localStorage`，不用 Cookie——因为 SSE 走 `fetch` 手工读流带 header（见票 12），走 Cookie 反而要额外处理 CSRF。
