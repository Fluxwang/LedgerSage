# 03 — diff 卡显示插入点上文

**What to build:** 在「即将写入的 diff」卡里，绿色的 `+` 行上方用灰色显示插入点之前的几行已有原文，就像 `git diff` 的上下文行。上文直接放进 `preview()` 和 `preview_budget()` 的回执里，不新开 `/ledger/raw`；这样上文和插入行号是在同一次 reload 里算出来的，不会错位。同时删掉 `/ledger/raw` 的占位卡片和 `ledgerSlice`。

详见 spec 的「diff 卡上文」一节。

**Blocked by:** None — can start immediately

**Status:** done

- [x] `Settings` 新增 `ledger_context_lines`，默认值 5
- [x] `preview()` 和 `preview_budget()` 的回执增加 `context_before: string[]`，内容是插入点之前最多 N 行原文；如果取到的全是空行，就继续往上取，直到拿到非空内容或者到文件开头；文件为空或不存在时返回 `[]`
- [x] 回放时，pending 写入的回执也会带上上文；终态写入的回执里没有这个字段，前端按 `[]` 处理
- [x] diff 卡把上文显示成灰色、不带 `+` 号的行，行号从 `insert_at_line - context_before.length` 开始，和下面的 `+` 行接得上
- [x] 删除 `LedgerPanel` 里 `GET /ledger/raw` 的 `<Stub>`，以及 `api.ts` 的 `ledgerSlice` 和 `LedgerSlice`
- [x] 测试覆盖：非空文件上文的最后一行就是插入点前的原文；空文件返回 `[]`；插入点前全是空行时会继续往上取；预算预览也带上文
- [x] `pytest` 和 `npm run build` 都通过
- [x] 手工验证：连着记两笔相同的地铁，第二笔的 diff 卡上文里能看到第一笔，并且出现「疑似重复」提示

## 实现与验证

- 回执统一携带 context_before；与插入行号一起读取，包含追加时的分隔空行。空文件与禁用上文均返回空数组；纯空白窗口向前扩展。预算预览也重新加载账本。浏览器用连续两笔火锅交易验证灰色原文、连续行号和疑似重复提示；移除 raw 占位与客户端接口。
- 验证：全量 pytest 165 项通过；mypy 36 个源文件通过；npm run build 通过。
