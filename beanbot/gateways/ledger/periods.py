"""时间范围换算。"""

from __future__ import annotations

import datetime
from datetime import date, timedelta
from zoneinfo import ZoneInfo

BUDGET_PERIODS = ("weekly", "monthly", "yearly")


def today() -> date:
    return date.today()


def period_bounds(period: str, today: date | None = None) -> tuple[date, date]:
    """把页面时间范围（this_week/this_month/this_year）或预算周期（weekly/monthly/yearly）换算成闭区间。"""
    today = today or datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if period in ("this_week", "weekly"):
        return today - timedelta(days=today.weekday()), today
    if period in ("this_year", "yearly"):
        return date(today.year, 1, 1), today
    return today.replace(day=1), today
