"""流水端点：服务端筛选、可寻址的 id、删除与撤销（ADR 0013）。"""
import asyncio
from datetime import date

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from tests.test_api import settings
from tests.test_dashboard import expense, register


def seeded(tmp_path):
    app = create_app(settings(tmp_path))
    client = TestClient(app)
    headers = register(client)
    user = app.state.db.rows('SELECT * FROM users')[0]
    ledger = app.state.ledgers.get(user)
    today = date.today()
    asyncio.run(ledger.insert([
        expense(today, '128', '火锅店'),
        expense(today, '42', '滴滴出行', 'Expenses:Transport'),
        expense(today, '5600', '链家', 'Expenses:Other'),
    ], today=today))
    return app, client, headers, ledger


def test_transactions_are_filtered_paged_and_addressable(tmp_path):
    _, client, headers, _ = seeded(tmp_path)

    everything = client.get('/transactions', headers=headers).json()
    dining = client.get('/transactions?account=Expenses:Food', headers=headers).json()
    by_payee = client.get('/transactions?payee=滴滴', headers=headers).json()
    first_page = client.get('/transactions?size=2&page=1', headers=headers).json()
    second_page = client.get('/transactions?size=2&page=2', headers=headers).json()

    assert everything['total'] == 3
    assert everything['sum'] == '5770' and everything['currency'] == 'CNY'
    assert {row['payee'] for row in dining['rows']} == {'火锅店'}
    assert dining['total'] == 1
    assert [row['payee'] for row in by_payee['rows']] == ['滴滴出行']
    assert by_payee['rows'][0]['account'] == 'Expenses:Transport'
    assert by_payee['rows'][0]['from'] == 'Assets:WeChat:Balance'
    assert len(first_page['rows']) == 2 and len(second_page['rows']) == 1
    ids = [row['id'] for row in everything['rows']]
    assert len(set(ids)) == 3 and all(ids)


def test_delete_removes_the_entry_and_undo_puts_it_back(tmp_path):
    _, client, headers, ledger = seeded(tmp_path)
    target = next(row for row in client.get('/transactions', headers=headers).json()['rows']
                  if row['payee'] == '滴滴出行')

    raw = client.get(f"/transactions/{target['id']}/raw", headers=headers).json()
    deleted = client.delete(f"/transactions/{target['id']}", headers=headers)

    assert '滴滴出行' in raw['text']
    assert deleted.status_code == 200
    remaining = client.get('/transactions', headers=headers).json()
    assert remaining['total'] == 2
    assert '滴滴出行' not in (ledger.root / raw['file']).read_text()

    restored = client.post(f"/transactions/{deleted.json()['commit']}/undo", headers=headers)
    assert restored.status_code == 200
    assert client.get('/transactions', headers=headers).json()['total'] == 3


def test_a_stale_id_is_refused_over_http(tmp_path):
    _, client, headers, _ = seeded(tmp_path)
    # 列表是倒序的，rows[-1] 在文件最前面；删掉它，它后面所有交易的行号都会变
    rows = client.get('/transactions', headers=headers).json()['rows']
    stale = rows[0]['id']
    client.delete(f"/transactions/{rows[-1]['id']}", headers=headers)

    refused = client.delete(f"/transactions/{stale}", headers=headers)

    assert refused.status_code in (404, 409)
    assert client.get('/transactions', headers=headers).json()['total'] == 2


def test_another_user_cannot_read_or_delete_these_transactions(tmp_path):
    app, client, headers, _ = seeded(tmp_path)
    target = client.get('/transactions', headers=headers).json()['rows'][0]['id']
    app.state.db.invite('second-invite')  # 邀请码一次性，第二个用户得有自己的
    other = {'Authorization': "Bearer " + client.post(
        '/auth/register',
        json={'username': 'other', 'password': 'correct-horse', 'invite_code': 'second-invite'},
    ).json()['access_token']}

    # 每个用户一本账本，别人的 id 在自己账本里根本不存在（ADR 0005）
    assert client.get(f'/transactions/{target}/raw', headers=other).status_code == 404
    assert client.delete(f'/transactions/{target}', headers=other).status_code == 404
    assert client.get('/transactions', headers=headers).json()['total'] == 3
