# 02 — 账本健康度

**What to build:** 用户在编辑器里手改账本后，刷新页面就能在顶栏和统计页看到**账本健康度**：bean-check 是否通过、**工作区**是否干净、有几笔支出**缺收款方**。检查的是磁盘上此刻的账本，不是内存里的缓存；账本即使已经坏到无法加载，也照样能看到错在哪里。

第一步先做预重构：把「这个用户的账本根目录在哪里」（模板目录还是接入的 `ledger_path`）的判断，从账本工厂里抽成可复用的函数，行为不变。状态接口复用这个函数，绕过工厂和缓存，每次请求都对 `main.bean` 重新运行一遍 loader。这个接口只读，不拿写锁。

返回格式（来自 spec，前端预设类型里的 `file`、`currency`、`transaction_count` 都去掉）：

```jsonc
GET /ledger/status
{
  "bean_check": { "ok": false, "error_count": 2, "message": "2026/10-expenses.bean:14 Transaction does not balance" },
  "git": { "clean": true, "last_commit_at": "2026-10-14T21:03:00+08:00" },
  "health": [
    { "key": "bean_check" | "working_tree" | "missing_payee", "level": "ok" | "warn", "text": "…" }
  ]
}
```

**Blocked by:** None — can start immediately

**Status:** done

- [x] 预重构完成后，现有测试不改一行就能全部通过
- [x] 把一个 `.bean` 文件手改到不平衡，不重启服务，接口返回 `bean_check.ok == false`，`message` 指向出错的文件和行
- [x] `message` 里只有相对于账本根目录的路径，没有服务器上的绝对路径
- [x] 账本首次加载就失败的用户（工厂会拒绝这样的账本），这个接口仍然返回 200
- [x] 被跟踪的文件有改动，或者存在未跟踪的 `*.bean` 文件时，`clean == false`；只有未跟踪的 `foo.txt` 时，仍然是 `clean == true`
- [x] `last_commit_at` 是 HEAD 的提交时间
- [x] 缺收款方只统计方向为「支出」且没有 payee 的交易，按全账本累计；没有 payee 的转账不计入；数量大于 0 时这一项为 `warn`
- [x] 顶栏 chip：三项都 ok 时显示绿色「bean-check ✓ · N 小时前提交」；有任意 warn 时显示琥珀色，文字取第一条 warn 的 `text`；点击跳到统计页的健康度卡片
- [x] 统计页右栏「账本健康度」逐项列出 `health`，不再显示 `<Stub>`
- [x] 测试从 HTTP 层断言上面这些行为，直接在 `tmp_path` 里改写或新建文件来模拟手工编辑；`npm run build` 通过

## Comments

- 预重构：根目录解析抽至 `repo.ledger_root`，原有 100 项测试未修改且全部通过。
- 已完成：`GET /ledger/status` 不经过工厂缓存、不拿写锁；使用已锁定 Beancount 3.2.3 的无缓存加载入口，避免 loader 的 pickle 缓存读写。升级 Beancount 时需复核此入口。git status 禁用可选索引刷新。
- HTTP 测试覆盖磁盘改坏后重新检查、相对路径、首次加载失败、未跟踪文件与已暂存改动、HEAD 时间、全账本缺收款方统计、用户隔离、未初始化目录只读检查及 main.bean 缺失。
- 浏览器验证通过：绿色 / 琥珀色 chip、首条警告、点击滚动并聚焦健康度卡片；仪表盘无法读取时健康度仍可见。顶栏与卡片共用请求，切区间不重查健康度。
- 验证：全量 pytest 111 项通过；mypy 检查通过；`npm run build` 通过。Windows 下 pytest 使用 `python -X utf8 -m pytest -q`，本地补齐 tzdata 与类型检查依赖；临时页面验证服务修正了本机 .js MIME 映射。
