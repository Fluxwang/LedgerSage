"""确定性的账本、仪表盘与撤销端点。"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field

from beanbot.api.auth import CurrentUser
from beanbot.gateways.ledger import Ledger, period_bounds
from beanbot.gateways.ledger.repo import ledger_root
from beanbot.gateways.ledger.status import ledger_status

router = APIRouter()

CARD_PREFIXES = ("Assets:", "Liabilities:")
PAGE_PERIODS = ("this_week", "this_month", "this_year")
PAGE_SIZE = 10
TREND_MONTHS = 6
TRANSACTIONS_PAGE_SIZE = 20
# 流水页在内存里筛选，先划一条上限免得整本账本都进来。
TRANSACTIONS_LIMIT = 5000


def shape(row: dict) -> dict:
    """把两条分录压成流水页要的「转入 / 转出」两栏。"""
    postings = row["postings"]
    debit = next(
        (item for item in postings if item["amount"] and Decimal(item["amount"]) > 0),
        None,
    )
    credit = next(
        (item for item in postings if item["amount"] and Decimal(item["amount"]) < 0),
        None,
    )
    return {
        "account": (debit or {}).get("account", ""),
        "from": (credit or {}).get("account", ""),
        "flagged": not row["payee"],
    }


def user_ledger(request: Request, user: dict) -> Ledger:
    return request.app.state.ledgers.get(user)


@router.get("/ledger/status")
def status(request: Request, user: CurrentUser):
    """独立检查磁盘上的账本，损坏的账本仍返回可读的体检结果。"""
    return ledger_status(ledger_root(request.app.state.settings, user))


def trend_months(today: date, count: int = TREND_MONTHS) -> list[date]:
    """最近 count 个自然月的月初，从早到晚。"""
    months: list[date] = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(date(year, month, 1))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(months))


@router.get("/accounts")
async def accounts(
    request: Request, user: CurrentUser, prefix: str = ""
):
    return [
        {"account": account, "display_name": display_name}
        for account, display_name in user_ledger(request, user).accounts_with_names()
        if account.startswith(prefix)
    ]


@router.post("/transactions/{commit}/undo")
async def undo(commit: str, request: Request, user: CurrentUser):
    """撤销一次 LedgerSage 提交——记账、预算、删除都走这一条（ADR 0013）。"""
    return await user_ledger(request, user).undo(commit)


@router.get("/transactions")
async def transactions(
    request: Request,
    user: CurrentUser,
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
    account: Annotated[str, Query()] = "",
    tag: Annotated[str, Query()] = "",
    payee: Annotated[str, Query()] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = TRANSACTIONS_PAGE_SIZE,
):
    """流水页：服务端筛选与分页，每笔带可寻址的 id。"""
    ledger = user_ledger(request, user)
    rows = ledger.query_transactions(
        start or date(1970, 1, 1),
        end or date.today(),
        account or None,
        payee or None,
        limit=TRANSACTIONS_LIMIT,
    )
    wanted = tag.lstrip("#")
    if wanted:
        rows = [row for row in rows if wanted in row["tags"]]
    window = rows[(page - 1) * size : page * size]
    return {
        "rows": [row | shape(row) for row in window],
        "page": page,
        "size": size,
        "total": len(rows),
        "sum": str(sum(Decimal(row["amount"]) for row in rows)),
        "currency": ledger.operating_currency,
    }


@router.get("/transactions/{transaction_id}/raw")
async def transaction_raw(
    transaction_id: str, request: Request, user: CurrentUser
):
    """删除确认弹窗要展示的账本原文。"""
    return user_ledger(request, user).transaction_source(transaction_id)


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str, request: Request, user: CurrentUser
):
    """从账本原文里移除整笔交易；返回的 commit 可以喂给 undo（ADR 0013）。"""
    return await user_ledger(request, user).delete(transaction_id)


@router.get("/dashboard")
async def dashboard(
    request: Request,
    user: CurrentUser,
    period: Annotated[str, Query()] = "this_month",
    # page: int = Query(1, ge=1),
    page: Annotated[int, Query(ge=1)] = 1,
):
    ledger = user_ledger(request, user)
    today = date.today()
    period = period if period in PAGE_PERIODS else "this_month"
    start, end = period_bounds(period, today)
    names = dict(ledger.accounts_with_names())
    balances = ledger.movement(date(1970, 1, 1), today)
    changes = ledger.movement(start, end)
    cards = [
        {
            "account": account,
            "display_name": names.get(account) or account,
            "kind": "liability" if account.startswith("Liabilities:") else "asset",
            "balance": str(balances.get(account, Decimal())),
            "change": str(changes.get(account, Decimal())),
            "currency": ledger.operating_currency,
        }
        for account, _ in ledger.accounts_with_names()
        if account.startswith(CARD_PREFIXES)
    ]
    months = trend_months(today)
    monthly = ledger.monthly_expenses(months[0], today)
    trend = {
        month.strftime("%Y-%m"): monthly.get(month.strftime("%Y-%m"), Decimal())
        for month in months
    }
    categories = ledger.expense_totals(start, end)
    payees = ledger.payee_expenses(start, end)
    dawn = date(1970, 1, 1)
    total = sum(
        1 for transaction in ledger.transactions if dawn <= transaction.date <= today
    )
    rows = ledger.query_transactions(dawn, today, limit=page * PAGE_SIZE)
    return {
        "accounts": cards,
        "top_payees": [
            {"payee": payee, "amount": str(amount)}
            for payee, amount in sorted(
                payees.items(), key=lambda item: (-item[1], item[0])
            )[:10]
        ],
        "monthly_trend": [
            {"month": key, "amount": str(amount)} for key, amount in trend.items()
        ],
        "categories": [
            {
                "account": account,
                "display_name": names.get(account) or account,
                "amount": str(amount),
            }
            for account, amount in sorted(
                categories.items(), key=lambda item: item[1], reverse=True
            )
            if amount
        ],
        "recent": {
            "rows": rows[(page - 1) * PAGE_SIZE :],
            "page": page,
            "size": PAGE_SIZE,
            "total": total,
        },
        "budgets": ledger.budget_status(today),
        "period": {"start": start.isoformat(), "end": end.isoformat(), "name": period},
    }
