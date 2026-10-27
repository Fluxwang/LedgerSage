# 07 — 对话页 diff 卡显示 bean-check 结果

**What to build:** 对话页右栏「即将写入的 diff / 已写入的 diff」卡片的「校验」区，目前最后一行还是 `GET /ledger/status` 的「待接口」占位。这个接口在 02 已经做好了，这里只需要接上：在写入校验项下面显示账本此刻的 bean-check 结果，让用户在点「确认」之前就知道账本本身有没有问题。

这一处占位在最初统计时被漏掉了：当时只数了调用 `pending()` 的函数，没有数直接写在组件里的 `<Stub>`。

**Blocked by:** None — can start immediately（02 已完成）

**Status:** done

- [x] diff 卡的「校验」区不再出现 `<Stub>`，最后一行显示 bean-check 的状态：通过时显示 ✓「bean-check 通过」，失败时显示「!」和 `bean_check.message`（相对路径）
- [x] 复用顶栏已经取到的账本状态数据，不为 diff 卡单独发请求；确认写入、撤销或删除之后，diff 卡和顶栏同时刷新
- [x] bean-check 失败时，「确认」按钮本身不受影响：是否允许写入仍然由后端确认时的校验决定（ADR-0012），前端只负责提示
- [x] 账本状态还在加载或请求失败时，这一行显示「读取中」或失败信息，不影响 diff 和其他校验项的展示
- [x] `npm run build` 通过
- [ ] 手工验证：把一个 `.bean` 文件手改到不平衡，在对话里记一笔，diff 卡的校验区显示这条错误；改回之后刷新，显示「bean-check 通过」

## Comments

- 已实现：diff 卡「校验」区最后一行显示 bean-check 结果，复用顶栏的账本健康度请求；撤销现在也会触发刷新（确认、删除原本就会）。
- 验证：`npm run build` 通过。**浏览器手工验证还没做**，所以 Status 先不改成 done。
