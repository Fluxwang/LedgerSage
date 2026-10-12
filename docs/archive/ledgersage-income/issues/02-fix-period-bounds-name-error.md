# 02 — 修周期换算的 NameError

**What to build:** 预算与统计走到按周期换算日期区间的分支时不再抛异常。

周期换算函数在计算默认日期时引用了一个模块级导入，而该导入已被删除，导致这条分支一执行就抛 `NameError`。

与本期主线无关的独立缺陷，单独修、单独验证，不要和方向改造混在一起。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 不传显式日期调用周期换算不再抛异常
- [ ] 周（本周 / weekly）、月（monthly）、年（this_year / yearly）三种周期的边界都正确
- [ ] 覆盖这条分支的测试存在且在修复前是失败的