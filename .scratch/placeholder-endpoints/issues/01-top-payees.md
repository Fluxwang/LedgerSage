# 01 — 前十收款方

**What to build:** 统计页右栏的「前十收款方」显示当前区间内净支出最多的 10 个**收款方**。数据随 `/dashboard` 一起返回，区间和页面上其他数字一致，口径和分类合计一致（按 `Expenses:` 分录行的净额计算，退款会抵扣）。前端不再单独请求这份数据，「待接口」占位消失。

**Blocked by:** None — can start immediately

**Status:** done

- [x] `/dashboard` 的返回里多了 `top_payees: [{ payee, amount }]`，最多 10 条，按金额降序排列，区间就是 dashboard 的 `period`
- [x] 同一个收款方先支出 100、再退款 30，排行里显示 70
- [x] 没有 payee 的交易不进排行；只算账本主币种
- [x] 收款方按原文字符串精确分组，「星巴克」和「Starbucks」是两条（见 CONTEXT.md「收款方」）
- [x] 切换 `period` 后，排行跟着变化
- [x] 所有收款方金额之和不超过同区间分类合计之和
- [x] 前端删除独立的 top-payees 请求函数，右栏直接读 dashboard 数据，切换区间时不再多发一次请求
- [x] 测试从 HTTP 层断言上面这些行为，参照现有的仪表盘测试；`npm run build` 通过

## Comments

- 已完成：`/dashboard.top_payees` 复用分录行折叠逻辑，按主币种计算净支出、精确分组、降序取前十；前端直接读取 dashboard 数据。
- HTTP 测试覆盖退款抵扣、空收款方、多币种、原文分组、排行上限、区间切换和空账本。
- 浏览器验证通过：切到本周后排行变化，无独立 top-payees 请求。
- 验证：全量 pytest 111 项通过；mypy 检查通过；`npm run build` 通过。
