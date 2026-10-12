"""两段式写入：Agent 只产出 diff，落盘由用户确认（ADR 0012）。"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from beanbot.exceptions import LedgerWriteConflict, NotFound
from beanbot.gateways.ledger import LedgerFactory, TransactionInput
from beanbot.services.pending_service import PendingWriteService
from beanbot.storage.database import Database, now
from tests.test_api import settings


def prepared(tmp_path):
    config = settings(tmp_path)
    database = Database(config.database_path)
    user = {'id': uuid4().hex, 'username': 'mark', 'ledger_path': None}
    database.execute('INSERT INTO users VALUES(?,?,?,?,?)', (user['id'], user['username'], 'unused', None, now()))
    return database, user, LedgerFactory(config)


def transaction(**kwargs):
    return TransactionInput(amount=Decimal(kwargs.get('amount', '128')), date=kwargs.get('date', date(2026, 9, 9)),
                            payee=kwargs.get('payee', '火锅店'), narration='午饭',
                            from_account='Assets:WeChat:Balance', to_account='Expenses:Food:Dining')


async def test_edit_preview_then_confirm_uses_new_accounts(tmp_path):
    database, user, ledgers = prepared(tmp_path)
    service = PendingWriteService(database, ledgers)
    pending = database.create_pending(user['id'], None, 'record',
                                     {'transactions': [transaction().model_dump(mode='json')]})
    preview = service.edit(user, pending['id'], 0, {'from_account': 'Assets:Alipay:Balance'})
    assert 'Assets:Alipay:Balance' in preview['text']
    assert 'Assets:WeChat:Balance' not in preview['text']
    receipt = await service.confirm(user, pending['id'])
    assert receipt['text'] == preview['text']
    assert ledgers.get(user).transactions[0].postings[0].account == 'Assets:Alipay:Balance'


async def test_edit_validation_expiry_and_batch_isolation(tmp_path):
    from beanbot.exceptions import AccountNotFound

    database, user, ledgers = prepared(tmp_path)
    service = PendingWriteService(database, ledgers)
    payload = {'transactions': [transaction().model_dump(mode='json'), transaction(payee='另家').model_dump(mode='json')]}
    pending = database.create_pending(user['id'], None, 'record', payload)
    with pytest.raises(AccountNotFound):
        service.edit(user, pending['id'], 0, {'from_account': 'Assets:Missing'})
    assert database.pending(pending['id'], user['id'])['payload'] == payload
    preview = service.edit(user, pending['id'], 0, {'to_account': 'Income:Salary'})
    assert preview['transactions'][0]['from_account'] == 'Income:Salary'
    assert preview['transactions'][1]['from_account'] == 'Assets:WeChat:Balance'
    assert database.pending(pending['id'], user['id'])['created_at'] == pending['created_at']
    service.reject(user, pending['id'])
    with pytest.raises(LedgerWriteConflict):
        service.edit(user, pending['id'], 0, {'from_account': 'Assets:Cash'})
    stale = database.create_pending(user['id'], None, 'record', payload)
    database.execute('UPDATE pending_writes SET created_at=? WHERE id=?',
                     ((datetime.fromisoformat(now()) - timedelta(hours=25)).isoformat(), stale['id']))
    with pytest.raises(LedgerWriteConflict, match='超过 24 小时'):
        service.edit(user, stale['id'], 0, {'from_account': 'Assets:Cash'})


async def test_preview_renders_the_diff_without_touching_the_ledger(tmp_path):
    _, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)

    preview = ledger.preview([transaction()], today=date(2026, 9, 9))

    assert preview['file'] == '2026/09-expenses.bean'
    assert preview['kind'] == 'record'
    assert preview['added_lines'][0] == '2026-09-09 * "火锅店" "午饭"'
    assert [check['level'] for check in preview['validations']] == ['ok', 'ok']
    assert ledger.transactions == []
    # 账本按当天月份初始化，九月的文件可能根本不存在；无论哪种情况都不能被写入内容。
    target = ledger.root / '2026' / '09-expenses.bean'
    assert not target.exists() or target.read_text() == ''


async def test_preview_flags_a_same_day_same_payee_same_amount_duplicate(tmp_path):
    _, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)
    await ledger.insert([transaction()], today=date(2026, 9, 9))

    warnings = [check for check in ledger.preview([transaction()])['validations'] if check['level'] == 'warn']

    assert len(warnings) == 1
    assert '疑似重复' in warnings[0]['text']


async def test_confirm_writes_once_and_a_second_confirm_is_refused(tmp_path):
    database, user, ledgers = prepared(tmp_path)
    service = PendingWriteService(database, ledgers)
    pending = database.create_pending(user['id'], None, 'record',
                                      {'transactions': [transaction().model_dump(mode='json')]})

    receipt = await service.confirm(user, pending['id'])

    assert receipt['commit'] and receipt['status'] == 'confirmed'
    assert len(ledgers.get(user).transactions) == 1
    with pytest.raises(LedgerWriteConflict, match='已经写入账本了'):
        await service.confirm(user, pending['id'])
    assert len(ledgers.get(user).transactions) == 1


async def test_rejected_and_expired_previews_never_reach_the_ledger(tmp_path):
    database, user, ledgers = prepared(tmp_path)
    service = PendingWriteService(database, ledgers)
    payload = {'transactions': [transaction().model_dump(mode='json')]}
    rejected = database.create_pending(user['id'], None, 'record', payload)
    stale = database.create_pending(user['id'], None, 'record', payload)
    long_ago = (datetime.fromisoformat(now()) - timedelta(hours=25)).isoformat()
    database.execute('UPDATE pending_writes SET created_at=? WHERE id=?', (long_ago, stale['id']))

    assert service.reject(user, rejected['id'])['status'] == 'rejected'
    with pytest.raises(LedgerWriteConflict, match='已经丢弃了'):
        await service.confirm(user, rejected['id'])
    with pytest.raises(LedgerWriteConflict, match='超过 24 小时'):
        await service.confirm(user, stale['id'])
    assert ledgers.get(user).transactions == []
    assert database.pending(stale['id'], user['id'])['status'] == 'expired'


async def test_another_user_cannot_confirm_someone_elses_pending_write(tmp_path):
    database, user, ledgers = prepared(tmp_path)
    other = {'id': uuid4().hex, 'username': 'other', 'ledger_path': None}
    database.execute('INSERT INTO users VALUES(?,?,?,?,?)', (other['id'], other['username'], 'unused', None, now()))
    service = PendingWriteService(database, ledgers)
    pending = database.create_pending(user['id'], None, 'record',
                                      {'transactions': [transaction().model_dump(mode='json')]})

    with pytest.raises(NotFound):
        await service.confirm(other, pending['id'])
    assert ledgers.get(user).transactions == []


async def test_budget_preview_warns_about_the_value_it_will_override(tmp_path):
    database, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)
    await ledger.set_budget('Expenses:Food:Dining', Decimal('1500'), effective_date=date(2026, 1, 1))

    preview = ledger.preview_budget('Expenses:Food:Dining', Decimal('1800'))

    assert preview['file'] == 'budgets.bean'
    assert '1500.00 CNY' in preview['validations'][1]['text']
    assert ledger.budgets()[0]['amount'] == '1500.00'
    service = PendingWriteService(database, ledgers)
    pending = database.create_pending(user['id'], None, 'budget',
                                      {'account': 'Expenses:Food:Dining', 'amount': '1800', 'period': 'monthly'})
    await service.confirm(user, pending['id'])
    assert ledgers.get(user).budgets()[0]['amount'] == '1800.00'


def test_confirm_endpoint_is_what_actually_writes_the_ledger(tmp_path):
    """走完整的 HTTP 链路：对话只出 diff，确认才落盘（ADR 0012）。"""
    from fastapi.testclient import TestClient

    from beanbot.api.app import create_app
    from tests.test_dashboard import register
    from tests.test_graph import FixtureModel
    from tests.test_runs import converse

    app = create_app(settings(tmp_path), agent_model=FixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'thread-1', '火锅128')  # 缺付款账户，先追问
        events = converse(client, headers, 'thread-1', '微信')
        receipt = next(event for event in events if event['type'] == 'receipt')
        ledger = app.state.ledgers.get(app.state.db.rows('SELECT * FROM users')[0])

        assert receipt['pending_id'] and 'commit' not in receipt
        assert receipt['insert_at_line'] == 1
        assert client.get('/transactions', headers=headers).json()['total'] == 0

        confirmed = client.post(f"/chat/pending/{receipt['pending_id']}/confirm", headers=headers)
        assert confirmed.status_code == 200 and confirmed.json()['commit']
        ledger.reload()
        assert client.get('/transactions', headers=headers).json()['total'] == 1

        again = client.post(f"/chat/pending/{receipt['pending_id']}/confirm", headers=headers)
        assert again.status_code == 409
        assert client.get('/transactions', headers=headers).json()['total'] == 1


def test_reject_endpoint_discards_the_preview(tmp_path):
    from fastapi.testclient import TestClient

    from beanbot.api.app import create_app
    from tests.test_dashboard import register
    from tests.test_graph import FixtureModel
    from tests.test_runs import converse

    app = create_app(settings(tmp_path), agent_model=FixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'thread-1', '火锅128')
        events = converse(client, headers, 'thread-1', '微信')
        receipt = next(event for event in events if event['type'] == 'receipt')

        rejected = client.post(f"/chat/pending/{receipt['pending_id']}/reject", headers=headers)

        assert rejected.json()['status'] == 'rejected'
        assert client.post(f"/chat/pending/{receipt['pending_id']}/confirm", headers=headers).status_code == 409
        assert client.get('/transactions', headers=headers).json()['total'] == 0