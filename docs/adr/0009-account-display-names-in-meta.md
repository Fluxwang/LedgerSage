# 账户的中文显示名迁移到 `name:` meta

存量账本把账户的中文名写成行尾注释（`2019-12-04 open Expenses:Food:Breakfast ;早餐`），而 `loader.load_file()` 会丢弃注释——这批语义信息在文件里肉眼可见，在代码里完全不存在。我们用一次性脚本把它们迁移成 Beancount meta：

```beancount
2019-12-04 open Expenses:Food:Breakfast
  name: "早餐"
```

## Consequences

- 这首先是**准确率**问题，其次才是展示问题。Extract 在几十个账户里选一个时，看到 `Expenses:Food:Dining / Lunch / DrinkFruit` 是在猜，看到 `晚餐 / 午餐 / 饮料水果` 才是在读。喂给 LLM 的账户列表因此带上显示名。
- 仪表盘的中文类目名与 Agent 读到的是同一个来源，账本仍是唯一真源。
- 迁移会改动用户既有的账本文件，必须先提交 git 再跑，且脚本要可回滚。
- 新增账户此后必须写 `name:` meta，行尾注释不再被系统识别。
- 被否决的替代方案是绕过 loader 正则扫行尾注释：不动用户数据，但会留下第二条账本解析路径，且注释写法一变就失效。
