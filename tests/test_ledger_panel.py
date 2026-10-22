"""右栏上文和写入历史从 HTTP 获取真实账本内容。"""
import asyncio
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.gateways.ledger.repo import git
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_pending_writes import transaction
from tests.test_runs import RoutingFixtureModel, converse


def ledger_for(app, client, headers):
    user = app.state.db.rows('SELECT * FROM users WHERE id=?',
                             (client.get('/auth/me', headers=headers).json()['id'],))[0]
    return app.state.ledgers.get(user)


@pytest.mark.parametrize('budget', [False, True])
@pytest.mark.parametrize('body', ['', '; 最近的交易\n', '; 最近的交易\n' + '\n' * 8])
def test_preview_context_and_replay(tmp_path, budget, body):
    from tests.test_budget import BudgetFixtureModel
    model = BudgetFixtureModel() if budget else RoutingFixtureModel()
    app = create_app(settings(tmp_path), agent_model=model)
    with TestClient(app) as client:
        headers = register(client)
        ledger = ledger_for(app, client, headers)
        target = ledger.root / ('budgets.bean' if budget else ledger.target_file())
        target.write_text(body, encoding='utf-8')
        events = converse(client, headers, 'context', '设置餐饮预算' if budget else '火锅128')
        if not budget:
            events = converse(client, headers, 'context', '微信')
        receipt = next(e for e in events if e['type'] == 'receipt')
        context = receipt['context_before']
        if body:
            assert any('最近的交易' in line for line in context)
            # 包括写入时新增的分隔空行，显示的行号必须能对应到账本原文。
            original = (body + '\n').splitlines()
            assert context == original[receipt['insert_at_line'] - len(context) - 1:receipt['insert_at_line'] - 1]
        else:
            assert context == []
        replay = client.get('/sessions/context/runs', headers=headers).json()
        assert replay['runs'][0]['pending_writes'][0]['receipt']['context_before'] == context


def test_history_actions_undo_legacy_manual_limit_and_isolation(tmp_path):
    config = settings(tmp_path)
    app = create_app(config, agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        ledger = ledger_for(app, client, headers)
        assert client.get('/ledger/history', headers=headers).json() == []
        recorded = asyncio.run(ledger.insert([transaction(), transaction(payee='地铁', amount='6')]))
        budget = asyncio.run(ledger.set_budget('Expenses:Food:Dining', Decimal('2000')))
        removed = asyncio.run(ledger.delete(ledger.transaction_id(ledger.transactions[0])))
        asyncio.run(ledger.undo(removed['commit']))
        asyncio.run(ledger.insert([transaction(payee='旧系统')]))
        git(ledger.root, 'commit', '--amend', '-m', 'BeanChat: record 1 transaction(s)')
        legacy = git(ledger.root, 'rev-parse', 'HEAD')
        (ledger.root / 'notes.txt').write_text('手工记录', encoding='utf-8')
        git(ledger.root, 'add', 'notes.txt')
        git(ledger.root, 'commit', '-m', 'manual')
        rows = client.get('/ledger/history', headers=headers).json()
        assert [r['commit'] for r in rows] == [legacy, removed['commit'], budget['commit'], recorded['commit']]
        assert [r['kind'] for r in rows] == ['record', 'delete', 'budget', 'record']
        assert rows[1]['undone_at'] and all(r['undone_at'] is None for r in (rows[0], rows[2], rows[3]))
        assert rows[3]['summary'] == '09-09 火锅店/午饭 −128 等 2 笔'
        assert rows[2]['summary'] == '餐饮 预算 → 2000.00 CNY'
        assert '火锅店' in rows[1]['summary']
        assert all(r['file'] and r['committed_at'] for r in rows)
        app.state.settings.ledger_history_limit = 2
        assert len(client.get('/ledger/history', headers=headers).json()) == 2
        assert client.get('/ledger/history').status_code == 401
        app.state.db.invite('second')
        other = client.post('/auth/register', json={
            'username': 'other', 'password': 'correct-horse', 'invite_code': 'second',
        }).json()
        assert client.get('/ledger/history', headers={'Authorization': f"Bearer {other['access_token']}"}).json() == []


@pytest.mark.parametrize('context_lines', [0, 2])
def test_duplicate_preview_uses_real_transaction_context(tmp_path, context_lines):
    config = settings(tmp_path).model_copy(update={'ledger_context_lines': context_lines})
    app = create_app(config, agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'duplicate', '火锅128')
        first = converse(client, headers, 'duplicate', '微信')
        pending = next(e['pending_id'] for e in first if e['type'] == 'receipt')
        assert client.post(f'/chat/pending/{pending}/confirm', headers=headers).status_code == 200
        second = converse(client, headers, 'duplicate', '火锅128')
        receipt = next(e for e in second if e['type'] == 'receipt')
        assert any('疑似重复' in v['text'] for v in receipt['validations'])
        assert len(receipt['context_before']) == context_lines
