"""账本目录的 git 操作与初始脚手架。"""

from __future__ import annotations

import asyncio
import subprocess
from datetime import date
from pathlib import Path

ACCOUNT_FILES = {
    "assets.bean": [
        ("Assets:Cash", "现金"),
        ("Assets:WeChat:Balance", "微信"),
        ("Assets:Alipay:Balance", "支付宝"),
        ("Assets:DebitCard:A", "银行卡A"),
    ],
    "liabilities.bean": [("Liabilities:CreditCard", "信用卡")],
    "expenses.bean": [
        ("Expenses:Food:Dining", "餐饮"),
        ("Expenses:Transport", "交通"),
        ("Expenses:Other", "其他支出"),
    ],
    "income.bean": [("Income:Salary", "工资")],
    "equity.bean": [("Equity:Opening-Balances", "期初余额")],
}


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], check=True, text=True, capture_output=True
    )
    return completed.stdout.strip()


def init_repo(root: Path) -> None:
    if not (root / ".git").is_dir():
        git(root, "init", "-q")
    git(root, "config", "user.name", "BeanChat Agent")
    git(root, "config", "user.email", "agent@beanchat.local")


async def commit_only(root: Path, message: str, *paths: str) -> str:
    """只提交给定路径（不带上工作区其他改动），返回新的 HEAD。"""
    await asyncio.to_thread(git, root, "add", *paths)
    await asyncio.to_thread(
        git, root, "commit", "-q", "--only", "-m", message, "--", *paths
    )
    return await asyncio.to_thread(git, root, "rev-parse", "HEAD")


def scaffold_ledger(root: Path, today: date | None = None) -> None:
    """生成可立即使用、可审计的最小账本。"""
    today = today or date.today()
    root.mkdir(parents=True, exist_ok=True)
    (root / "accounts").mkdir(exist_ok=True)
    (root / str(today.year)).mkdir(exist_ok=True)
    main = (
        'option "title" "BeanChat Ledger"\n'
        'option "operating_currency" "CNY"\n'
        'include "accounts/*.bean"\n'
        'include "budgets.bean"\n'
        'include "20*/*.bean"\n'
    )
    (root / "main.bean").write_text(main, encoding="utf-8")
    opened_on = date(1970, 1, 1)
    for filename, accounts in ACCOUNT_FILES.items():
        body = "".join(
            f'{opened_on.isoformat()} open {account}\n  name: "{display_name}"\n\n'
            for account, display_name in accounts
        )
        (root / "accounts" / filename).write_text(body, encoding="utf-8")
    (root / "budgets.bean").write_text("", encoding="utf-8")
    # 向量索引跟着账本走，但它是派生数据，不进版本库（票 21）。
    (root / ".gitignore").write_text("vector.sqlite\n", encoding="utf-8")
    initial_transactions = Path(str(today.year)) / f"{today.month:02d}-expenses.bean"
    (root / initial_transactions).write_text("", encoding="utf-8")
    init_repo(root)
    git(
        root,
        "add",
        "main.bean",
        "accounts",
        "budgets.bean",
        ".gitignore",
        initial_transactions.as_posix(),
    )
    git(root, "commit", "-q", "-m", "BeanChat: initialize ledger")
