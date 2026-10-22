# 05 — 统计页去掉「持仓」和「BQL 查询」

**What to build:** 删掉统计页子导航里那两个永远点不了的灰色 tab。持仓不在产品范围内；BQL 不暴露给用户，原因见 ADR 0006。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 删除 `web/src/explore/Explore.tsx` 子导航里「持仓」和「BQL 查询」两个 `div.off`
- [x] 删除 `web/src/explore/explore.css` 里不再使用的 `.subnav .off` 样式
- [x] `npm run build` 通过
- [x] 手工验证：统计页子导航只剩「收支表 / 资产负债 / 流水」和右侧的「在对话里追问这张表」

## 实现与验证

- 已删除持仓、BQL 查询两个灰色 tab 与对应样式；浏览器确认导航仅保留收支表、资产负债、流水及追问入口。
- 验证：全量 pytest 165 项通过；mypy 36 个源文件通过；npm run build 通过。
