"""预算分支：追加写入、按预算自身周期统计执行情况。"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.gateways.ledger import LedgerFactory, TransactionInput
from beanbot.services.agent.classify import Classification
from beanbot.services.agent.graph import AgentGraph
from beanbot.services.agent.model import BudgetPlan, QueryPlan
from beanbot.services.chat_service import ChatService
from beanbot.storage.database import Database, now
from tests.test_api import settings
from tests.test_dashboard import expense, register
from tests.test_graph import FixtureModel, confirm_all


def test_default_period_bounds_use_shanghai_today():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from beanbot.gateways.ledger import period_bounds

    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    for period in ("weekly", "this_week"):
        assert period_bounds(period) == (today - timedelta(days=today.weekday()), today)
    assert period_bounds("monthly") == (today.replace(day=1), today)
    for period in ("yearly", "this_year"):
        assert period_bounds(period) == (date(today.year, 1, 1), today)


class BudgetFixtureModel(FixtureModel):
    async def classify(self, message, history):
        return Classification(intent="budget", confidence=0.95)


class BudgetAskFixtureModel(BudgetFixtureModel):
    async def budget(self, message, accounts):
        if message == "设个预算":
            return BudgetPlan()
        return BudgetPlan(account="Expenses:Food:Dining", amount=Decimal("2000"))


class BudgetQueryFixtureModel(FixtureModel):
    async def classify(self, message, history):
        return Classification(intent="query", confidence=0.95)

    async def query(self, message, accounts, today):
        return QueryPlan(tool="budget_status")


def graph_service(config, database, ledgers, model):
    return ChatService(
        database, AgentGraph(config, database, ledgers, model), "fixture"
    )


def prepared(tmp_path):
    config = settings(tmp_path)
    database = Database(config.database_path)
    user = {"id": uuid4().hex, "username": "mark", "ledger_path": None}
    database.execute(
        "INSERT INTO users VALUES(?,?,?,?,?)",
        (user["id"], user["username"], "unused", None, now()),
    )
    return config, database, user, LedgerFactory(config)


async def test_budget_intent_appends_a_commit_per_adjustment(tmp_path):
    config, database, user, ledgers = prepared(tmp_path)
    service = graph_service(config, database, ledgers, BudgetFixtureModel())

    events = [
        event
        async for event in service.stream(
            user, "budget-thread", "给餐饮设个每月2000的预算"
        )
    ]

    assert [
        event["type"] for event in events if event["type"] in ("receipt", "message")
    ] == ["receipt", "message"]
    ledger = ledgers.get(user)
    assert ledger.budgets() == []  # 预览阶段还没写进账本
    await confirm_all(database, ledgers, user, events)
    ledger.reload()
    assert ledger.budgets() == [
        {
            "account": "Expenses:Food:Dining",
            "period": "monthly",
            "amount": "2000.00",
            "currency": "CNY",
            "effective_date": date.today().isoformat(),
        }
    ]
    assert not ledger.errors
    assert database.rows("SELECT intent FROM runs")[0]["intent"] == "budget"


async def test_budget_without_account_or_amount_asks_before_writing(tmp_path):
    config, database, user, ledgers = prepared(tmp_path)
    service = graph_service(config, database, ledgers, BudgetAskFixtureModel())

    first = [event async for event in service.stream(user, "budget-ask", "设个预算")]

    assert first[-1]["type"] == "ask"
    assert ledgers.get(user).budgets() == []
    second = [event async for event in service.stream(user, "budget-ask", "餐饮两千")]
    assert any(event["type"] == "receipt" for event in second)
    await confirm_all(database, ledgers, user, second)
    assert ledgers.get(user).budgets()[0]["amount"] == "2000.00"


async def test_query_branch_reports_budget_execution(tmp_path):
    config, database, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)
    today = date.today()
    await ledger.insert([expense(today, "128", "火锅店")], today=today)
    await ledger.set_budget(
        "Expenses:Food:Dining", Decimal("2000"), effective_date=today.replace(day=1)
    )
    service = graph_service(config, database, ledgers, BudgetQueryFixtureModel())

    events = [
        event
        async for event in service.stream(user, "budget-query", "餐饮预算还剩多少")
    ]

    messages = [event["content"] for event in events if event["type"] == "message"]
    assert messages == ["餐饮：已用 128 / 上限 2000.00，剩余 1872.00。"]


def test_dashboard_scopes_usage_to_the_budget_period(tmp_path):
    app = create_app(settings(tmp_path))
    today = date.today()
    month_start = today.replace(day=1)
    earlier_month = (month_start - timedelta(days=1)).replace(day=1)
    with TestClient(app) as client:
        headers = register(client)
        user = app.state.db.rows("SELECT id,username,ledger_path FROM users")[0]
        ledger = app.state.ledgers.get(user)
        asyncio.run(ledger.insert([expense(today, "128", "火锅店")], today=today))
        asyncio.run(
            ledger.insert(
                [expense(earlier_month, "900", "年夜饭")], today=earlier_month
            )
        )
        asyncio.run(
            ledger.set_budget(
                "Expenses:Food:Dining", Decimal("2000"), effective_date=earlier_month
            )
        )

        yearly_view = client.get("/dashboard?period=this_year", headers=headers).json()

    budget = yearly_view["budgets"][0]
    assert budget["used"] == "128" and budget["remaining"] == "1872.00"
    assert budget["window"] == {
        "start": month_start.isoformat(),
        "end": today.isoformat(),
    }
