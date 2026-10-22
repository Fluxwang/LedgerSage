"""查询图使用真实账户、按段匹配，并明确回复的查询口径。"""
from datetime import date
from decimal import Decimal

import pytest

from beanbot.services.agent.graph import AgentGraph
from beanbot.services.agent.model import QueryPlan
from beanbot.services.agent.query import TransactionQuery
from tests.test_api import settings
from tests.test_graph import QueryFixtureModel
from tests.test_pending_writes import prepared, transaction


async def query(tmp_path, plan, message='餐饮花了多少', populated=True):
    database, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)
    with (ledger.root / 'accounts/expenses.bean').open('a', encoding='utf-8') as stream:
        stream.write('\n1970-01-01 open Expenses:FoodDelivery\n')
    ledger.reload()
    if populated:
        await ledger.insert([transaction(amount='128')])
        await ledger.insert([transaction().model_copy(update={
            'amount': Decimal('20'), 'to_account': 'Expenses:FoodDelivery',
        })])

    class Model(QueryFixtureModel):
        async def query(self, message, accounts, today):
            assert ('Expenses:Food:Dining', '餐饮') in accounts
            assert not any(a.startswith('Equity:') for a, _ in accounts)
            return plan

    graph = AgentGraph(settings(tmp_path), database, ledgers, Model())
    return await graph.query({'user': user, 'message': message}), ledger


def plan_for(tool, prefix):
    if tool == 'query_transactions':
        return QueryPlan(tool=tool, arguments=TransactionQuery(
            start=date(2026, 9, 1), end=date(2026, 9, 9), account_prefix=prefix))
    return QueryPlan(tool=tool, account_prefix=prefix, as_of=date(2026, 9, 9))


@pytest.mark.parametrize('tool', ['query_transactions', 'get_balance', 'list_accounts'])
@pytest.mark.parametrize('prefix', ['Expenses:Food', ' Expenses:Food: '])
async def test_all_tools_match_segments(tmp_path, tool, prefix):
    result, _ = await query(tmp_path, plan_for(tool, prefix))
    assert 'Expenses:FoodDelivery' not in str(result['query_result'])
    assert 'Expenses:Food:Dining' in str(result['query_result'])
    assert result['receipt']['arguments'] == plan_for(tool, prefix).model_dump(mode='json')


@pytest.mark.parametrize('tool', ['query_transactions', 'get_balance', 'list_accounts'])
@pytest.mark.parametrize('prefix,message,expected', [
    ('Expenses:Dining', '餐饮花了多少', '餐饮（Expenses:Food:Dining）'),
    ('Expenses:Restaurant', '餐饮花了多少', '餐饮（Expenses:Food:Dining）'),
    ('ZZZZZZZZ', '查询', '可以问我『我有哪些账户』'),
    ('Expenses:Fo', '查询', '账本里没有 `Expenses:Fo` 这个账户'),
])
async def test_unknown_prefix_does_not_execute_query(tmp_path, monkeypatch, tool, prefix, message, expected):
    from beanbot.gateways.ledger import Ledger
    def forbidden(*args, **kwargs):
        raise AssertionError('不存在的账户不能执行查询')
    monkeypatch.setattr(Ledger, 'query_transactions', forbidden)
    monkeypatch.setattr(Ledger, 'balances', forbidden)
    result, _ = await query(tmp_path, plan_for(tool, prefix), message, populated=False)
    assert expected in result['reply']
    assert result['query_result']['error'] == 'account_not_found'
    assert len(result['query_result']['candidates']) <= 3
    assert result['receipt']['arguments'] == plan_for(tool, prefix).model_dump(mode='json')


@pytest.mark.parametrize('prefix,label,total,count', [
    ('Expenses:Food:Dining', '餐饮（Expenses:Food:Dining）', '128.00', 1),
    ('Expenses:Food', 'Expenses:Food ', '128.00', 1),
    ('Expenses:FoodDelivery', 'Expenses:FoodDelivery ', '20.00', 1),
    (None, '', '148.00', 2),
    (':', '', '148.00', 2),
])
@pytest.mark.parametrize('populated', [False, True])
async def test_reply_states_dates_and_account(tmp_path, prefix, label, total, count, populated):
    result, _ = await query(tmp_path, plan_for('query_transactions', prefix), populated=populated)
    scope = f'2026-09-01 至 2026-09-09，{label}'
    expected = f'{scope}共 {count} 笔，支出合计 {total}。' if populated else f'{scope}没有记录。'
    assert result['reply'] == expected
