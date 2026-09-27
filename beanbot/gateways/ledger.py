"""按用户隔离的 Beancount 账本与安全写入原语。"""

from __future__ import annotations

import asyncio
import base64
import binascii
import datetime
import hashlib
import re
import subprocess
from collections import OrderedDict
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

from beancount import loader
from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.number import D
from beancount.parser.printer import EntryPrinter
from pydantic import BaseModel, Field, model_validator

from beanbot.config import Settings
from beanbot.exceptions import AccountNotFound, LedgerWriteConflict, NotFound


Direction = Literal['支出', '收入', '转账']


def flow_direction(from_account: str | None, to_account: str | None) -> Direction | None:
    """由两条分录行的账户前缀推导方向；两侧都定不下来时返回 None（ADR 0014）。"""
    if (to_account or '').startswith('Expenses:'):
        return '支出'
    if (from_account or '').startswith('Income:'):
        return '收入'
    return '转账' if from_account and to_account else None


class TransactionInput(BaseModel):
    amount: Decimal = Field(gt=0)
    date: date
    payee: str = Field(min_length=1)
    narration: str = ""
    from_account: str = Field(min_length=1)
    to_account: str = Field(min_length=1)
    tags: set[str] = Field(default_factory=set)

    @model_validator(mode="after")
    def normalize_flow(self):
        if self.to_account.startswith('Income:'):
            self.from_account, self.to_account = self.to_account, self.from_account
        if self.from_account == self.to_account or self.to_account.startswith('Income:'):
            raise ValueError('两条分录行不能表示这笔资金流向')
        return self

    @property
    def direction(self) -> Direction:
        return flow_direction(self.from_account, self.to_account) or '转账'


ACCOUNT_FILES = {
    "assets.bean": [
        ("Assets:Cash", "现金"),
        ("Assets:WeChat:Balance", "微信"),
        ("Assets:Alipay:Balance", "支付宝"),
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


BUDGET_PERIODS = ("weekly", "monthly", "yearly")

# 交易 id = base64url("<相对路径>:<行号>:<摘要>")。摘要是规范渲染文本的 SHA-256 前八位，
# 用来在删除前确认「这一行还是我当初看到的那一笔」。详见 ADR 0013。
ID_SEPARATOR = ":"


def encode_transaction_id(relative: str, lineno: int, digest: str) -> str:
    raw = f"{relative}{ID_SEPARATOR}{lineno}{ID_SEPARATOR}{digest}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_transaction_id(transaction_id: str) -> tuple[str, int, str]:
    padded = transaction_id + "=" * (-len(transaction_id) % 4)
    try:
        relative, lineno, digest = (
            base64.urlsafe_b64decode(padded).decode().rsplit(ID_SEPARATOR, 2)
        )
        return relative, int(lineno), digest
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise NotFound("交易 id 不合法") from exc


def _today() -> date:
    return date.today()


def period_bounds(period: str, today: date | None = None) -> tuple[date, date]:
    """把页面时间范围（this_week/this_month/this_year）或预算周期（weekly/monthly/yearly）换算成闭区间。"""
    today = today or datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if period in ("this_week", "weekly"):
        return today - timedelta(days=today.weekday()), today
    if period in ("this_year", "yearly"):
        return date(today.year, 1, 1), today
    return today.replace(day=1), today


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        # stdout=subprocess.PIPE,
        # stderr=subprocess.PIPE,
        capture_output=True,
    )
    return completed.stdout.strip()


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
    if not (root / ".git").is_dir():
        _git(root, "init", "-q")
    _git(root, "config", "user.name", "BeanChat Agent")
    _git(root, "config", "user.email", "agent@beanchat.local")
    _git(
        root,
        "add",
        "main.bean",
        "accounts",
        "budgets.bean",
        ".gitignore",
        initial_transactions.as_posix(),
    )
    _git(root, "commit", "-q", "-m", "BeanChat: initialize ledger")


class Ledger:
    def __init__(self, root: Path, user_id: str):
        self.root = root.resolve()
        self.user_id = user_id
        self._lock = asyncio.Lock()
        self.reload()

    def reload(self) -> None:
        self._entries, self.errors, self.options = loader.load_file(
            str(self.root / "main.bean")
        )
        self._printer = EntryPrinter(dcontext=self.options.get("dcontext"))

    @property
    def accounts(self) -> set[str]:
        return {
            entry.account for entry in self._entries if isinstance(entry, data.Open)
        }

    def accounts_with_names(self) -> list[tuple[str, str | None]]:
        return sorted(
            (entry.account, (entry.meta or {}).get("name"))
            for entry in self._entries
            if isinstance(entry, data.Open)
        )

    @property
    def transactions(self) -> list[data.Transaction]:
        return [entry for entry in self._entries if isinstance(entry, data.Transaction)]

    def transaction_history(self) -> list[tuple[str, str, str]]:
        history: list[tuple[str, str, str]] = []
        for transaction in self.transactions:
            postings = transaction.postings
            if len(postings) != 2 or any(p.account.startswith('Equity:') or p.units is None or p.cost or p.price for p in postings):
                continue
            source = next((p for p in postings if p.units and p.units.number is not None and p.units.number < 0), None)
            target = next((p for p in postings if p.units and p.units.number is not None and p.units.number > 0), None)
            if source and target and source.units and target.units and source.units.currency == target.units.currency:
                history.append((transaction.payee or transaction.narration or '', source.account, target.account))
        return history

    def query_transactions(
        self,
        start: date,
        end: date,
        account_prefix: str | None = None,
        payee: str | None = None,
        limit: int = 100,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        group_by: str = "none",
    ) -> list[dict]:
        result: list[dict[str, Any]] = []
        for transaction in reversed(self.transactions):
            if not start <= transaction.date <= end:
                continue
            if payee and payee.casefold() not in (transaction.payee or "").casefold():
                continue
            postings = [
                posting
                for posting in transaction.postings
                if not account_prefix or posting.account.startswith(account_prefix)
            ]
            if account_prefix and not postings:
                continue
            amounts = [
                abs(cast(Decimal, posting.units.number))
                for posting in transaction.postings
                if posting.units
            ]
            transaction_amount = max(amounts, default=Decimal())
            if min_amount is not None and transaction_amount < min_amount:
                continue
            if max_amount is not None and transaction_amount > max_amount:
                continue
            result.append(
                {
                    "id": self.transaction_id(transaction),
                    "date": transaction.date.isoformat(),
                    "payee": transaction.payee,
                    "narration": transaction.narration,
                    "tags": sorted(transaction.tags or ()),
                    "amount": str(transaction_amount),
                    "currency": self.operating_currency,
                    "postings": [
                        {
                            "account": posting.account,
                            "amount": str(posting.units.number)
                            if posting.units
                            else None,
                            "currency": posting.units.currency
                            if posting.units
                            else None,
                        }
                        for posting in postings
                    ],
                }
            )
            if len(result) >= limit:
                break
        if group_by != "none":
            grouped: dict[str, Decimal] = {}
            for row in result:
                if group_by == "day":
                    key = row["date"]
                elif group_by == "month":
                    key = row["date"][:7]
                elif group_by == "payee":
                    key = row["payee"] or ""
                else:
                    key = row["postings"][0]["account"] if row["postings"] else ""
                values = [
                    abs(Decimal(item["amount"]))
                    for item in row["postings"]
                    if item["amount"]
                ]
                grouped[key] = grouped.get(key, Decimal()) + max(
                    values, default=Decimal()
                )
            return [
                {"group": key, "amount": str(amount)}
                for key, amount in sorted(grouped.items())
            ]
        return result

    def balances(
        self, prefix: str = "", as_of: date | None = None
    ) -> dict[str, dict[str, str]]:
        totals: dict[str, dict[str, Decimal]] = {}
        for transaction in self.transactions:
            if as_of and transaction.date > as_of:
                continue
            for posting in transaction.postings:
                if not posting.account.startswith(prefix) or not posting.units:
                    continue
                currencies = totals.setdefault(posting.account, {})
                number = cast(Decimal, posting.units.number)
                currencies[posting.units.currency] = (
                    currencies.get(posting.units.currency, Decimal()) + number
                )
        return {
            account: {currency: str(amount) for currency, amount in values.items()}
            for account, values in totals.items()
        }

    def budgets(self) -> list[dict]:
        """每个账户取生效日期最新的那条预算；周期改了也只有最新一条算数（ADR-0008）。"""
        latest: dict[str, dict] = {}
        for entry in self._entries:
            if (
                not isinstance(entry, data.Custom)
                or entry.type != "budget"
                or len(entry.values) < 3
            ):
                continue
            account_value, period_value, amount_value = (
                getattr(item, "value", item) for item in entry.values[:3]
            )
            account = str(account_value)
            period = str(period_value)
            amount = getattr(amount_value, "number", D("0"))
            currency = getattr(amount_value, "currency", "CNY")
            value = {
                "account": account,
                "period": period,
                "amount": str(amount),
                "currency": currency,
                "effective_date": entry.date.isoformat(),
            }
            if (
                account not in latest
                or value["effective_date"] > latest[account]["effective_date"]
            ):
                latest[account] = value
        return sorted(latest.values(), key=lambda item: item["account"])

    @property
    def operating_currency(self) -> str:
        currencies = self.options.get("operating_currency")
        return currencies[0] if currencies else "CNY"

    def _fold_postings(
        self,
        start: date,
        end: date,
        key: Callable[[data.Transaction, data.Posting], str],
        prefix: str = "",
    ) -> dict[str, Decimal]:
        """区间内按 key 汇总本位币记账额；金额保持符号，退款才能把支出冲回去。"""
        totals: dict[str, Decimal] = {}
        currency = self.operating_currency
        for transaction in self.transactions:
            if not start <= transaction.date <= end:
                continue
            for posting in transaction.postings:
                if not posting.units or posting.units.currency != currency:
                    continue
                if not posting.account.startswith(prefix):
                    continue
                bucket = key(transaction, posting)
                totals[bucket] = totals.get(bucket, Decimal()) + cast(
                    Decimal, posting.units.number
                )
        return totals

    def expense_totals(self, start: date, end: date) -> dict[str, Decimal]:
        """区间内按支出账户汇总的净支出。"""
        return self._fold_postings(
            start, end, lambda _, posting: posting.account, "Expenses:"
        )

    def monthly_expenses(self, start: date, end: date) -> dict[str, Decimal]:
        """区间内按 YYYY-MM 汇总的净支出，用于趋势图。"""
        return self._fold_postings(
            start,
            end,
            lambda transaction, _: transaction.date.strftime("%Y-%m"),
            "Expenses:",
        )

    def movement(self, start: date, end: date) -> dict[str, Decimal]:
        """区间内每个账户的净变动；全区间即为余额。"""
        return self._fold_postings(start, end, lambda _, posting: posting.account)

    def budget_status(self, today: date | None = None) -> list[dict]:
        """每条预算按自身周期统计已用与剩余，与页面选择的时间范围无关。"""
        today = today or date.today()
        names = dict(self.accounts_with_names())
        rows: list[dict] = []
        for budget in self.budgets():
            start, end = period_bounds(budget["period"], today)
            totals = self.expense_totals(start, end)
            used = sum(
                (
                    amount
                    for account, amount in totals.items()
                    if account == budget["account"]
                    or account.startswith(budget["account"] + ":")
                ),
                Decimal(),
            )
            rows.append(
                budget
                | {
                    "display_name": names.get(budget["account"]) or budget["account"],
                    "used": str(used),
                    "remaining": str(Decimal(budget["amount"]) - used),
                    "window": {"start": start.isoformat(), "end": end.isoformat()},
                }
            )
        return rows

    # ---------------------------------------------------------------- 定位分录

    def _digest(self, entry: data.Directive) -> str:
        """对规范渲染文本取摘要，跟源文件的缩进、空行风格无关。"""
        return hashlib.sha256(self.render_entry(entry).encode("utf-8")).hexdigest()[:8]

    def _relative(self, filename: str) -> str:
        return Path(filename).resolve().relative_to(self.root).as_posix()

    def transaction_id(self, entry: data.Transaction) -> str:
        meta = entry.meta or {}
        return encode_transaction_id(
            self._relative(meta["filename"]), int(meta["lineno"]), self._digest(entry)
        )

    def find(self, transaction_id: str) -> data.Transaction:
        """按 id 找回那一笔；账本变过（摘要对不上）就报冲突而不是删错行。"""
        relative, lineno, digest = decode_transaction_id(transaction_id)
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root):
            raise NotFound("交易不在这本账本里")
        for entry in self.transactions:
            meta = entry.meta or {}
            if not meta.get("filename") or int(meta.get("lineno", 0)) != lineno:
                continue
            if Path(meta["filename"]).resolve() != target:
                continue
            if self._digest(entry) != digest:
                raise LedgerWriteConflict("这笔交易已经变了，请刷新后重试")
            return entry
        raise NotFound("找不到这笔交易")

    def _source_block(self, entry: data.Directive) -> tuple[Path, int, int]:
        """分录在源文件里占据的行区间（0-based，右开），末尾空行不算。"""
        meta = entry.meta or {}
        path = Path(meta["filename"]).resolve()
        start = int(meta["lineno"]) - 1
        following = [
            int((other.meta or {}).get("lineno", 0)) - 1
            for other in self._entries
            if (other.meta or {}).get("filename")
            and Path(other.meta["filename"]).resolve() == path
            and int((other.meta or {}).get("lineno", 0)) - 1 > start
        ]
        lines = path.read_text(encoding="utf-8").splitlines()
        end = min(following) if following else len(lines)
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        return path, start, end

    def transaction_source(self, transaction_id: str) -> dict:
        """删除确认弹窗要展示的账本原文。"""
        entry = self.find(transaction_id)
        path, start, end = self._source_block(entry)
        lines = path.read_text(encoding="utf-8").splitlines()
        return {
            "file": self._relative(str(path)),
            "start_line": start + 1,
            "end_line": end,
            "text": "\n".join(lines[start:end]),
        }

    # ---------------------------------------------------------------- 写入预览

    def _duplicates(self, batch: Iterable[TransactionInput]) -> list[dict]:
        """同一天、同一收款方、同一金额——多半是重复记账或者导入重了。"""
        warnings: list[dict] = []
        for candidate in batch:
            for existing in self.transactions:
                if existing.date != candidate.date:
                    continue
                if (existing.payee or "") != candidate.payee:
                    continue
                amounts = {
                    abs(cast(Decimal, posting.units.number))
                    for posting in existing.postings
                    if posting.units
                }
                if candidate.amount in amounts:
                    warnings.append(
                        {
                            "level": "warn",
                            "text": f"与 {existing.date.isoformat()} 另一笔 "
                            f"{candidate.amount} 相似，疑似重复",
                        }
                    )
                    break
        return warnings

    def target_file(self, today: date | None = None) -> Path:
        """按写入当天决定落到哪个月的文件，不能在 bootstrap 时算死。"""
        current = today or _today()
        directory = Path(str(current.year))
        if (self.root / directory / '0-default').is_dir():
            directory /= '0-default'
        return directory / f"{current.month:02d}-expenses.bean"

    def _insert_position(self, relative: Path) -> int:
        target = self.root / relative
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        return existing.count("\n") + (2 if existing else 1)

    def preview(
        self, transactions: Iterable[TransactionInput], today: date | None = None
    ) -> dict:
        """渲染将要写入的文本与校验结果，一个字节都不落盘（ADR 0012）。"""
        self.reload()
        batch = self._validate(transactions)
        if not batch:
            raise LedgerWriteConflict("交易批次不能为空")
        relative = self.target_file(today)
        rendered = [self.render_transaction(transaction) for transaction in batch]
        text = "\n\n".join(rendered)
        return {
            "kind": "record",
            "file": relative.as_posix(),
            "insert_at_line": self._insert_position(relative),
            "entries": rendered,
            "text": text,
            "added_lines": text.split("\n"),
            "balanced": True,
            "validations": [
                {"level": "ok", "text": "借贷相抵为 0"},
                {"level": "ok", "text": "账户已在 open 指令中声明"},
                *self._duplicates(batch),
            ],
        }

    def budget_line(
        self,
        account: str,
        amount: Decimal,
        period: str = "monthly",
        effective_date: date | None = None,
        currency: str = "CNY",
    ) -> str:
        return (
            f'{(effective_date or _today()).isoformat()} custom "budget" '
            f'{account} "{period}" {amount:.2f} {currency}'
        )

    def preview_budget(
        self,
        account: str,
        amount: Decimal,
        period: str = "monthly",
        effective_date: date | None = None,
        currency: str = "CNY",
    ) -> dict:
        self._validate_budget(account, amount, period)
        line = self.budget_line(account, amount, period, effective_date, currency)
        current = next(
            (
                budget
                for budget in self.budgets()
                if budget["account"] == account and budget["period"] == period
            ),
            None,
        )
        validations = [{"level": "ok", "text": "账户已在 open 指令中声明"}]
        if current:
            validations.append(
                {
                    "level": "warn",
                    "text": f"当前生效的是 {current['amount']} {current['currency']}，"
                    f"这条会从 {(effective_date or _today()).isoformat()} 起覆盖它",
                }
            )
        return {
            "kind": "budget",
            "account": account,
            "file": "budgets.bean",
            "insert_at_line": self._insert_position(Path("budgets.bean")),
            "entries": [line],
            "text": line,
            "added_lines": [line],
            "balanced": True,
            "validations": validations,
        }

    # ------------------------------------------------------------------ 删除

    async def delete(self, transaction_id: str) -> dict:
        """从账本原文里移除整笔交易并提交。这是唯一一处读—改—写（ADR 0013）。"""
        async with self._lock:
            entry = self.find(transaction_id)
            path, start, end = self._source_block(entry)
            relative = self._relative(str(path))
            original = path.read_text(encoding="utf-8")
            lines = original.splitlines(keepends=True)
            removed = "".join(lines[start:end]).strip("\n")
            kept = "".join(lines[:start] + lines[end:])
            kept = re.sub(r"\n{3,}", "\n\n", kept).strip("\n")
            try:
                path.write_text(kept + "\n" if kept else "", encoding="utf-8")
                await asyncio.to_thread(_git, self.root, "add", relative)
                await asyncio.to_thread(
                    _git,
                    self.root,
                    "commit",
                    "-q",
                    "--only",
                    "-m",
                    f"BeanChat: delete transaction {entry.date.isoformat()} "
                    f"{entry.payee or entry.narration}",
                    "--",
                    relative,
                )
                commit = await asyncio.to_thread(self._git_head)
            except (OSError, subprocess.CalledProcessError) as exc:
                path.write_text(original, encoding="utf-8")
                raise LedgerWriteConflict(f"删除失败：{exc}") from exc
            self.reload()
            return {
                "commit": commit,
                "file": relative,
                "removed_lines": end - start,
                "text": removed,
            }

    def _git_head(self) -> str:
        return _git(self.root, "rev-parse", "HEAD")

    def render_entry(self, entry: data.Directive) -> str:
        """把账本里已有的分录渲染回规范文本。"""
        return self._printer(entry).strip()

    def render_transaction(
        self, transaction: TransactionInput, currency: str = "CNY"
    ) -> str:
        entry = data.Transaction(
            meta=data.new_metadata("<generated>", 0),
            date=transaction.date,
            flag="*",
            payee=transaction.payee,
            narration=transaction.narration,
            tags=frozenset(transaction.tags),
            links=frozenset(),
            postings=[
                data.Posting(
                    transaction.from_account,
                    Amount(-transaction.amount, currency),
                    None,
                    None,
                    None,
                    None,
                ),
                data.Posting(transaction.to_account, None, None, None, None, None),
            ],
        )
        return self._printer(entry).strip()

    def _validate(
        self, transactions: Iterable[TransactionInput]
    ) -> list[TransactionInput]:
        batch = list(transactions)
        accounts = self.accounts
        for index, transaction in enumerate(batch, 1):
            for field in ("from_account", "to_account"):
                account = getattr(transaction, field)
                if account not in accounts:
                    raise AccountNotFound(
                        f"第 {index} 笔的 {field} 账户不存在：{account}"
                    )
        return batch

    async def insert(
        self, transactions: Iterable[TransactionInput], today: date | None = None
    ) -> dict:
        """整批追加并提交；同一本账本的并发调用严格串行。"""
        async with self._lock:
            self.reload()
            batch = self._validate(transactions)
            if not batch:
                raise LedgerWriteConflict("交易批次不能为空")
            relative = self.target_file(today)
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            rendered = [self.render_transaction(transaction) for transaction in batch]
            before = target.stat().st_size if target.exists() else 0
            prefix = "\n" if before else ""
            try:
                with target.open("a", encoding="utf-8") as stream:
                    stream.write(prefix + "\n\n".join(rendered) + "\n")
                await asyncio.to_thread(_git, self.root, "add", relative.as_posix())
                await asyncio.to_thread(
                    _git,
                    self.root,
                    "commit",
                    "-q",
                    "--only",
                    "-m",
                    f"BeanChat: record {len(batch)} transaction(s)",
                    "--",
                    relative.as_posix(),
                )
                commit = await asyncio.to_thread(_git, self.root, "rev-parse", "HEAD")
            except (OSError, subprocess.CalledProcessError) as exc:
                if target.exists():
                    with target.open("r+b") as stream:
                        stream.truncate(before)
                raise LedgerWriteConflict(f"账本写入失败：{exc}") from exc
            self.reload()
            first_line = (
                target.read_text(encoding="utf-8")[:before].count("\n")
                + 1
                + bool(prefix)
            )
            return {
                "file": relative.as_posix(),
                "line": first_line,
                "commit": commit,
                "entries": rendered,
                "text": "\n\n".join(rendered),
            }

    async def undo(self, commit: str) -> dict:
        async with self._lock:
            try:
                resolved = await asyncio.to_thread(
                    _git, self.root, "rev-parse", "--verify", f"{commit}^{{commit}}"
                )
                subject = await asyncio.to_thread(
                    _git, self.root, "show", "-s", "--format=%s", resolved
                )
                if not subject.startswith(
                    ("BeanChat: record", "BeanChat: set budget", "BeanChat: delete")
                ):
                    raise LedgerWriteConflict("只能撤销 BeanChat 创建的提交")
                changed = (
                    await asyncio.to_thread(
                        _git,
                        self.root,
                        "diff-tree",
                        "--no-commit-id",
                        "--name-only",
                        "-r",
                        resolved,
                    )
                ).splitlines()
                await asyncio.to_thread(
                    _git, self.root, "revert", "--no-commit", resolved
                )
                await asyncio.to_thread(
                    _git,
                    self.root,
                    "commit",
                    "-q",
                    "--only",
                    "-m",
                    f"BeanChat: undo {resolved[:12]}",
                    "--",
                    *changed,
                )
            except subprocess.CalledProcessError as exc:
                raise LedgerWriteConflict("无法撤销该提交") from exc
            self.reload()
            return {"commit": resolved, "reverted": True}

    def _validate_budget(self, account: str, amount: Decimal, period: str) -> None:
        if account not in self.accounts:
            raise AccountNotFound(f"预算账户不存在：{account}")
        if amount <= 0:
            raise LedgerWriteConflict("预算金额必须大于零")
        if period not in BUDGET_PERIODS:
            raise LedgerWriteConflict("预算周期必须是 weekly、monthly 或 yearly")

    async def set_budget(
        self,
        account: str,
        amount: Decimal,
        period: str = "monthly",
        effective_date: date | None = None,
        currency: str = "CNY",
    ) -> dict:
        self._validate_budget(account, amount, period)
        async with self._lock:
            target = self.root / "budgets.bean"
            line = (
                self.budget_line(account, amount, period, effective_date, currency)
                + "\n"
            )
            before = target.stat().st_size if target.exists() else 0
            with target.open("a", encoding="utf-8") as stream:
                stream.write(("\n" if before else "") + line)
            try:
                await asyncio.to_thread(_git, self.root, "add", "budgets.bean")
                await asyncio.to_thread(
                    _git,
                    self.root,
                    "commit",
                    "-q",
                    "--only",
                    "-m",
                    f"BeanChat: set budget for {account}",
                    "--",
                    "budgets.bean",
                )
                commit = await asyncio.to_thread(_git, self.root, "rev-parse", "HEAD")
            except subprocess.CalledProcessError as exc:
                with target.open("r+b") as stream:
                    stream.truncate(before)
                raise LedgerWriteConflict("预算写入失败") from exc
            self.reload()
            return {"commit": commit, "file": "budgets.bean", "line": line.strip()}


class LedgerFactory:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: OrderedDict[str, Ledger] = OrderedDict()

    def get(self, user: dict) -> Ledger:
        user_id = str(user["id"])
        if user_id in self._cache:
            ledger = self._cache.pop(user_id)
            self._cache[user_id] = ledger
            return ledger
        root = Path(user.get("ledger_path") or self.settings.ledger_root / user_id)
        if user.get("ledger_path"):
            if not (root / "main.bean").is_file():
                raise LedgerWriteConflict("接管路径缺少 main.bean")
            if not (root / ".git").is_dir():
                _git(root, "init", "-q")
                _git(root, "config", "user.name", "BeanChat Agent")
                _git(root, "config", "user.email", "agent@beanchat.local")
        elif not (root / "main.bean").exists():
            scaffold_ledger(root)
        ledger = Ledger(root, user_id)
        if ledger.errors:
            raise LedgerWriteConflict(f"账本无法加载：{ledger.errors[0]}")
        self._cache[user_id] = ledger
        while len(self._cache) > self.settings.ledger_cache_size:
            self._cache.popitem(last=False)
        return ledger
