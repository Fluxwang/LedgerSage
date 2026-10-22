# 05 — 统计页去掉「持仓」和「BQL 查询」

**What to build:** 删掉统计页子导航里那两个永远点不了的灰色 tab。持仓不在产品范围内；BQL 不暴露给用户，原因见 ADR 0006。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 删除 `web/src/explore/Explore.tsx` 子导航里「持仓」和「BQL 查询」两个 `div.off`
- [ ] 删除 `web/src/explore/explore.css` 里不再使用的 `.subnav .off` 样式
- [ ] `npm run build` 通过
- [ ] 手工验证：统计页子导航只剩「收支表 / 资产负债 / 流水」和右侧的「在对话里追问这张表」
