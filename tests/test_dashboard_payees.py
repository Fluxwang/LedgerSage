"""通过 HTTP 验证收款方排行与仪表盘共用区间和净支出口径。"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_graph import FixtureModel


def test_payees_net_refunds_keep_exact_names_and_ignore_other_currencies(tmp_path):
    app = create_app(settings(tmp_path), agent_model=FixtureModel())
    today = date.today()
    with TestClient(app) as client:
        headers = register(client)
        user = app.state.db.rows('SELECT id,ledger_path FROM users')[0]
        ledger = app.state.ledgers.get(user)
        target = ledger.root / ledger.target_file(today)
        rows = [
            ('星巴克', '100', 'CNY'), ('星巴克', '-30', 'CNY'),
            ('Starbucks', '40', 'CNY'), ('', '20', 'CNY'),
            ('美元商店', '999', 'USD'),
        ]
        target.write_text(''.join(
            f'{today} * "{payee}" "测试"\n'
            f'  Expenses:Food:Dining  {amount} {currency}\n'
            f'  Assets:Cash  {-Decimal(amount)} {currency}\n\n'
            for payee, amount, currency in rows
        ), encoding='utf-8')
        ledger.reload()
        response = client.get('/dashboard', headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['top_payees'] == [
        {'payee': '星巴克', 'amount': '70'},
        {'payee': 'Starbucks', 'amount': '40'},
    ]
    assert sum(Decimal(row['amount']) for row in body['top_payees']) <= sum(
        Decimal(row['amount']) for row in body['categories']
    )


def test_payees_limit_sorting_and_period_switch(tmp_path):
    app = create_app(settings(tmp_path), agent_model=FixtureModel())
    today = date.today()
    # 本周之前的数据不应混入本周排行，即使与本周同月。
    earlier = today - timedelta(days=today.weekday() + 1)
    with TestClient(app) as client:
        headers = register(client)
        user = app.state.db.rows('SELECT id,ledger_path FROM users')[0]
        ledger = app.state.ledgers.get(user)
        target = ledger.root / ledger.target_file(today)
        target.write_text(''.join(
            f'{day} * "{payee}" "测试"\n'
            f'  Expenses:Food:Dining  {amount} CNY\n'
            f'  Assets:Cash  {-amount} CNY\n\n'
            for day, payee, amount in [
                (today, f'商店{i}', i) for i in range(1, 13)
            ] + [(earlier, '上周商店', 500)]
        ), encoding='utf-8')
        ledger.reload()
        week = client.get('/dashboard?period=this_week', headers=headers).json()
        year = client.get('/dashboard?period=this_year', headers=headers).json()
    assert week['top_payees'] == [
        {'payee': f'商店{i}', 'amount': str(i)} for i in range(12, 2, -1)
    ]
    if earlier.year == today.year:
        assert year['top_payees'][0] == {'payee': '上周商店', 'amount': '500'}
    assert len(year['top_payees']) == 10


def test_empty_payees_and_authentication(tmp_path):
    app = create_app(settings(tmp_path), agent_model=FixtureModel())
    with TestClient(app) as client:
        assert client.get('/dashboard').status_code == 401
        assert client.get('/dashboard', headers=register(client)).json()['top_payees'] == []
