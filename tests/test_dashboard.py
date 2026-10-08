"""仪表盘聚合端点：数字必须与账本一致，空账本不得报错。"""
import asyncio
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.gateways.ledger import TransactionInput
from tests.test_api import settings


def register(client) -> dict:
    body = {'username': 'mark', 'password': 'correct-horse', 'invite_code': 'test-invite'}
    return {'Authorization': f"Bearer {client.post('/auth/register', json=body).json()['access_token']}"}


def expense(day: date, amount: str, payee: str, to_account: str = 'Expenses:Food:Dining') -> TransactionInput:
    return TransactionInput(
        amount=Decimal(amount), date=day, payee=payee, narration='',
        from_account='Assets:WeChat:Balance', to_account=to_account,
    )


def test_empty_ledger_renders_without_errors(tmp_path):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        body = client.get('/dashboard', headers=register(client)).json()
    assert body['categories'] == []
    assert body['recent'] == {'rows': [], 'page': 1, 'size': 10, 'total': 0}
    assert len(body['monthly_trend']) == 6
    assert {point['amount'] for point in body['monthly_trend']} == {'0'}
    cards = {card['account']: card for card in body['accounts']}
    assert cards['Assets:Cash'] == {
        'account': 'Assets:Cash', 'display_name': '现金', 'kind': 'asset',
        'balance': '0', 'change': '0', 'currency': 'CNY',
    }
    assert cards['Liabilities:CreditCard']['kind'] == 'liability'
    assert '支付宝' in {card['display_name'] for card in body['accounts']}
    assert 'Equity:Opening-Balances' not in cards


def test_totals_names_and_period_switching_match_the_ledger(tmp_path):
    app = create_app(settings(tmp_path))
    today = date.today()
    month_start = today.replace(day=1)
    with TestClient(app) as client:
        headers = register(client)
        user = app.state.db.rows('SELECT id,username,ledger_path FROM users')[0]
        ledger = app.state.ledgers.get(user)
        earlier_month = (month_start - timedelta(days=1)).replace(day=1)
        asyncio.run(ledger.insert([expense(today, '128', '火锅店')], today=today))
        asyncio.run(ledger.insert(
            [expense(earlier_month, '60', '地铁', 'Expenses:Transport')], today=earlier_month,
        ))

        this_month = client.get('/dashboard?period=this_month', headers=headers).json()
        this_year = client.get('/dashboard?period=this_year', headers=headers).json()

    assert this_month['categories'] == [
        {'account': 'Expenses:Food:Dining', 'display_name': '餐饮', 'amount': '128'},
    ]
    assert [item['display_name'] for item in this_year['categories']] == ['餐饮', '交通']
    assert this_month['period'] == {'start': month_start.isoformat(), 'end': today.isoformat(),
                                    'name': 'this_month'}
    wechat = next(card for card in this_month['accounts'] if card['account'] == 'Assets:WeChat:Balance')
    assert wechat['balance'] == '-188' and wechat['change'] == '-128'
    trend = {point['month']: point['amount'] for point in this_year['monthly_trend']}
    assert trend[today.strftime('%Y-%m')] == '128'
    assert this_year['recent']['total'] == 2
    assert this_year['recent']['rows'][0]['payee'] == '火锅店'


def test_refunds_net_out_of_the_totals(tmp_path):
    """退款是 Expenses 上的负数分录，聚合必须冲减而不是当成又一笔支出。"""
    app = create_app(settings(tmp_path))
    today = date.today()
    with TestClient(app) as client:
        headers = register(client)
        user = app.state.db.rows('SELECT id,username,ledger_path FROM users')[0]
        ledger = app.state.ledgers.get(user)
        asyncio.run(ledger.insert([expense(today, '128', '火锅店')], today=today))
        refund = TransactionInput(
            amount=Decimal('28'), date=today, payee='火锅店', narration='退款',
            from_account='Expenses:Food:Dining', to_account='Assets:WeChat:Balance',
        )
        asyncio.run(ledger.insert([refund], today=today))

        body = client.get('/dashboard', headers=headers).json()

    assert body['categories'] == [
        {'account': 'Expenses:Food:Dining', 'display_name': '餐饮', 'amount': '100'},
    ]
    trend = {point['month']: point['amount'] for point in body['monthly_trend']}
    assert trend[today.strftime('%Y-%m')] == '100'


def test_recent_pagination_walks_past_the_first_page(tmp_path):
    app = create_app(settings(tmp_path))
    today = date.today()
    with TestClient(app) as client:
        headers = register(client)
        user = app.state.db.rows('SELECT id,username,ledger_path FROM users')[0]
        ledger = app.state.ledgers.get(user)
        asyncio.run(ledger.insert(
            [expense(today, str(index + 1), f'商户{index}') for index in range(25)], today=today,
        ))

        first = client.get('/dashboard?page=1', headers=headers).json()['recent']
        third = client.get('/dashboard?page=3', headers=headers).json()['recent']

    assert first['total'] == 25 and len(first['rows']) == 10
    assert len(third['rows']) == 5
    assert {row['payee'] for row in first['rows']} & {row['payee'] for row in third['rows']} == set()
