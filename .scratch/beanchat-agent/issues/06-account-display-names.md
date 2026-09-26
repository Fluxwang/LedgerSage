# 06 · 账户显示名：注释迁移成 meta 并接入读取

Status: open
Milestone: M1
Blocked by: 04

## 背景

存量账本把中文名写成行尾注释（`2019-12-04 open Expenses:Food:Breakfast ;早餐`），而 `loader.load_file()` 丢弃注释——这批语义在文件里肉眼可见、在代码里完全不存在。这首先是**准确率**问题：Extract 看到 `Food:Dining / Lunch / DrinkFruit` 是在猜，看到 `晚餐 / 午餐 / 饮料水果` 才是在读。见 ADR-0009。

## 要做什么

- 一次性迁移脚本：扫描账本里所有 `open` 指令的行尾注释，转成 `name:` meta。
- 脚本必须：跑前检查工作区干净（否则拒绝执行）、只改 `open` 行、保留被注释掉的 `open` 行原样不动、输出一份改动清单。
- `BeancountRepository` 新增读取：`accounts_with_names()` 返回 `[(account, display_name)]`。
- 提供 `list_accounts` 工具与 Extract 上下文时一律带上显示名。

## 完成标准

- 在 `/mnt/f/Beancount` 的副本上跑通，`expenses.bean` 近百行 `open` 全部迁移，`git diff` 可读、可回滚。
- 迁移后 `loader.load_file` 无新增 error。
- 没有注释的账户 `display_name` 为 `None`，不报错。

## 注意

模板脚手架（票 04）生成的账户必须自带 `name:` meta，两边保持一致。
