"""固定查询参数、时间归一化和 BQL 生成。"""

from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from beanbot.gateways.ledger.accounts import normalize_prefix


class DateRange(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def valid_range(self):
        if self.start > self.end:
            raise ValueError("开始日期不得晚于结束日期")
        if (self.end - self.start).days > 366 * 5:
            raise ValueError("查询跨度不得超过 5 年")
        if self.end > date.today():
            raise ValueError("结束日期不得在未来")
        return self


PeriodName = Literal["this_month", "last_month", "this_week", "this_year"]


def normalize_period(value: str | DateRange, today: date | None = None) -> DateRange:
    if isinstance(value, DateRange):
        result = value
    else:
        today = today or date.today()
        if value == "this_month":
            result = DateRange(start=today.replace(day=1), end=today)
        elif value == "last_month":
            last_day = today.replace(day=1) - timedelta(days=1)
            result = DateRange(start=last_day.replace(day=1), end=last_day)
        elif value == "this_week":
            result = DateRange(start=today - timedelta(days=today.weekday()), end=today)
        elif value == "this_year":
            result = DateRange(start=date(today.year, 1, 1), end=today)
        elif match := re.fullmatch(r"last_n_days:(\d+)", value):
            days = int(match.group(1))
            if not 1 <= days <= 366 * 5:
                raise ValueError("天数超出范围")
            result = DateRange(start=today - timedelta(days=days - 1), end=today)
        else:
            raise ValueError("不支持的时间范围")
    reference = today or date.today()
    if result.end > reference:
        raise ValueError("结束日期不得在未来")
    return result


class TransactionQuery(BaseModel):
    # 用户没说时间范围时留空，默认查本月
    start: date | None = None
    end: date | None = None
    account_prefix: str | None = None
    payee: str | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    group_by: Literal["none", "day", "month", "account", "payee"] = "none"
    order_by: Literal["date", "amount_desc"] = "date"
    limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_dates(self):
        self.end = self.end or date.today()
        self.start = self.start or self.end.replace(day=1)
        DateRange(start=self.start, end=self.end)
        return self


def quote_bql(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_transaction_bql(query: TransactionQuery) -> str:
    clauses = [f"date >= {query.start.isoformat()}", f"date <= {query.end.isoformat()}"]
    prefix = normalize_prefix(query.account_prefix)
    if prefix:
        clauses.append(f"account ~ {quote_bql('^' + re.escape(prefix) + '(:|$)')}")
    if query.payee:
        clauses.append(f"payee ~ {quote_bql(re.escape(query.payee))}")
    if query.min_amount is not None:
        clauses.append(f"number(position) >= {query.min_amount}")
    if query.max_amount is not None:
        clauses.append(f"number(position) <= {query.max_amount}")
    fields = "date, payee, narration, account, position"
    return f"SELECT {fields} WHERE " + " AND ".join(clauses) + f" LIMIT {query.limit}"


def build_balance_bql(account_prefix: str, as_of: date) -> str:
    prefix = normalize_prefix(account_prefix)
    account_clause = f"account ~ {quote_bql('^' + re.escape(prefix) + '(:|$)')} AND " if prefix else ''
    return (
        "SELECT account, sum(position) "
        f"WHERE {account_clause}date <= {as_of.isoformat()} "
        "GROUP BY account"
    )


def scalar_amount(value) -> dict[str, str]:
    """把 Amount/Inventory 收敛为按币种分组的 JSON 值。"""
    if value is None or str(value) in ("", "()"):
        return {}
    positions = value.get_positions() if hasattr(value, "get_positions") else [value]
    result: dict[str, str] = {}
    for position in positions:
        units = getattr(position, "units", position)
        if hasattr(units, "currency") and hasattr(units, "number"):
            result[units.currency] = str(units.number)
    return result
