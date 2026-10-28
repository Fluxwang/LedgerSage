"""收支表：收入、支出两棵账户树 × 连续多个月的发生额矩阵。"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from beanbot.gateways.ledger.ledger import Ledger
from beanbot.gateways.ledger.periods import today

ROOTS = (("Income", "收入"), ("Expenses", "支出"))


def months_between(start: date, end: date) -> list[str]:
    """start 到 end 覆盖的自然月，YYYY-MM，从早到晚。"""
    months: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def income_statement(ledger: Ledger, start: date, end: date) -> dict:
    """按账户层级 × 月汇总区间内的发生额。

    Args:
        ledger: 要统计的账本
        start: 起始月的 1 日
        end: 截止日；早于当月最后一天或就是今天时，最后一列标为 partial
    Returns:
        currency、skipped_currencies、periods 与按深度优先排列的 rows；
        汇总账户含全部子孙及直接记在自身上的分录行，收入取正数，全零行剔除（根行保留）
    """
    prefixes = tuple(f"{root}:" for root, _ in ROOTS)
    months = months_between(start, end)
    column = {month: index for index, month in enumerate(months)}
    sign = {root: Decimal(-1) if root == "Income" else Decimal(1) for root, _ in ROOTS}

    # 每个分录行账户的每一级前缀都是树上的节点，汇总账户即便没开户也出现。
    cells: dict[str, list[Decimal]] = {root: [Decimal()] * len(months) for root, _ in ROOTS}
    for (month, account), amount in ledger.monthly_movement(start, end, prefixes).items():
        parts = account.split(":")
        for depth in range(1, len(parts) + 1):
            node = ":".join(parts[:depth])
            row = cells.setdefault(node, [Decimal()] * len(months))
            row[column[month]] += amount * sign[parts[0]]

    names = {account: name for account, name in ledger.accounts_with_names() if name}
    names.update(dict(ROOTS))
    children: dict[str, list[str]] = {}
    for node in cells:
        if ":" in node:
            children.setdefault(node.rsplit(":", 1)[0], []).append(node)

    def alive(node: str) -> bool:
        # 子孙在同月相抵时汇总行为零，但只要有子孙非零就得留着，否则下面的行会跟着消失。
        return any(cells[node]) or any(alive(child) for child in children.get(node, []))

    rows: list[dict] = []

    def visit(node: str, depth: int) -> None:
        rows.append({
            "account": node,
            "display_name": names.get(node) or node.rsplit(":", 1)[-1],
            "depth": depth,
            "cells": [f"{amount + Decimal():.2f}" for amount in cells[node]],
        })
        kept = [child for child in children.get(node, []) if alive(child)]
        for child in sorted(kept, key=lambda item: (-sum(cells[item]), item)):
            visit(child, depth + 1)

    for root, _ in ROOTS:
        visit(root, 0)

    last_day = calendar.monthrange(end.year, end.month)[1]
    periods: list[dict] = [{"period": month, "partial": False} for month in months]
    # 截到今天的当月即便是月末也还会有新流水，同样算没过完。
    if periods and (end.day < last_day or end == today()):
        periods[-1] = {"period": months[-1], "partial": True, "through": end.isoformat()}
    return {
        "currency": ledger.operating_currency,
        "skipped_currencies": ledger.skipped_currencies(start, end, prefixes),
        "periods": periods,
        "rows": rows,
    }
