"""历史对话通过 HTTP 回放，并恢复未完成的写入和追问。"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_runs import RoutingFixtureModel, converse


def test_list_replay_continue_and_isolation(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        assert client.get('/sessions', headers=headers).json() == []
        first = '请帮我看看这个月餐饮总共花了多少，我想了解实际支出'
        converse(client, headers, 'history', first)
        converse(client, headers, 'history', '这个月花了多少')
        rows = client.get('/sessions', headers=headers).json()
        assert rows[0]['title'] == first[:10]
        assert not rows[0]['has_pending_ask']
        replay = client.get('/sessions/history/runs', headers=headers).json()
        assert [run['message'] for run in replay['runs']] == [first, '这个月花了多少']
        assert all(run['steps'] and run['steps'][-1]['kicker'] == 'REPLY' for run in replay['runs'])
        old_id = replay['runs'][0]['id']
        app.state.db.execute('UPDATE runs SET message=NULL WHERE id=?', (old_id,))
        assert client.get('/sessions/history/runs', headers=headers).json()['runs'][0]['message'] is None
        app.state.db.invite('second')
        other = client.post('/auth/register', json={'username': 'other', 'password': 'correct-horse', 'invite_code': 'second'}).json()
        other_headers = {'Authorization': f"Bearer {other['access_token']}"}
        assert client.get('/sessions', headers=other_headers).json() == []
        assert client.get('/sessions/history/runs', headers=other_headers).status_code == 404
        assert client.get('/sessions/missing/runs', headers=headers).status_code == 404
        assert client.get('/sessions').status_code == 401


def test_pending_write_replay_confirm_reject_and_expiry(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        for thread in ['confirm', 'reject', 'expire']:
            converse(client, headers, thread, '火锅128')
            converse(client, headers, thread, '微信')
        def pending(thread):
            return client.get(f'/sessions/{thread}/runs', headers=headers).json()['runs'][0]['pending_writes'][0]
        record = pending('confirm')
        assert record['status'] == 'pending'
        changed = client.patch(f"/chat/pending/{record['id']}", headers=headers,
                               json={'transaction_index': 0, 'from_account': 'Assets:Alipay:Balance'})
        assert changed.status_code == 200
        assert 'Assets:Alipay:Balance' in pending('confirm')['receipt']['text']
        assert client.post(f"/chat/pending/{record['id']}/confirm", headers=headers).status_code == 200
        assert pending('confirm')['status'] == 'confirmed'
        assert pending('confirm')['commit_sha']
        assert client.get('/transactions', headers=headers).json()['total'] == 1
        rejected = pending('reject')
        client.post(f"/chat/pending/{rejected['id']}/reject", headers=headers)
        assert pending('reject')['status'] == 'rejected'
        expired = pending('expire')
        earlier = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        app.state.db.execute('UPDATE pending_writes SET created_at=? WHERE id=?', (earlier, expired['id']))
        assert pending('expire')['status'] == 'expired'
        assert client.post(f"/chat/pending/{expired['id']}/confirm", headers=headers).status_code == 409


def test_clarification_resume_and_expiry(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        first = converse(client, headers, 'ask', '火锅128')
        replay = client.get('/sessions/ask/runs', headers=headers).json()
        assert replay['has_pending_ask'] and replay['active_run_id'] == first[-1]['run_id']
        assert client.get('/sessions', headers=headers).json()[0]['has_pending_ask']
        resumed = converse(client, headers, 'ask', '微信')
        assert resumed[-1]['run_id'] == first[-1]['run_id']
        assert len(client.get('/sessions/ask/runs', headers=headers).json()['runs']) == 1
        assert not client.get('/sessions/ask/runs', headers=headers).json()['has_pending_ask']
        converse(client, headers, 'stale', '火锅128')
        earlier = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        app.state.db.execute("UPDATE sessions SET pending_at=? WHERE thread_id='stale'", (earlier,))
        replay = client.get('/sessions/stale/runs', headers=headers).json()
        assert not replay['has_pending_ask'] and replay['ask_expired']
        new = converse(client, headers, 'stale', '这个月花了多少')
        assert new[-1]['run_id'] != replay['active_run_id']
        assert len(client.get('/sessions/stale/runs', headers=headers).json()['runs']) == 2


def test_recent_limit_order_and_legacy_title(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        for index in range(31):
            converse(client, headers, f'thread-{index}', '这个月花了多少')
        rows = client.get('/sessions', headers=headers).json()
        assert len(rows) == 30 and rows[0]['thread_id'] == 'thread-30'
        assert 'thread-0' not in [row['thread_id'] for row in rows]
        app.state.db.execute("UPDATE sessions SET title='新对话' WHERE thread_id='thread-1'")
        converse(client, headers, 'thread-1', '这个月花了多少')
        rows = client.get('/sessions', headers=headers).json()
        assert rows[0]['thread_id'] == 'thread-1' and rows[0]['title'] == '新对话'


def drop_open(root, account):
    """模拟用户在编辑器里删掉某个账户的 open 指令（连同它的 name meta）。"""
    for path in (root / 'accounts').glob('*.bean'):
        blocks = path.read_text(encoding='utf-8').split('\n\n')
        path.write_text('\n\n'.join(b for b in blocks if f' open {account}' not in b), encoding='utf-8')


def test_replay_degrades_a_pending_write_whose_account_was_deleted(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'gone', '火锅128')
        converse(client, headers, 'gone', '微信')
        converse(client, headers, 'gone', '这个月餐饮花了多少')
        converse(client, headers, 'gone', '地铁6')
        converse(client, headers, 'gone', '微信')
        healthy_id = client.get('/sessions/gone/runs', headers=headers).json()['runs'][2]['pending_writes'][0]['id']
        moved = client.patch(f'/chat/pending/{healthy_id}', headers=headers,
                             json={'transaction_index': 0, 'to_account': 'Expenses:Transport'})
        assert moved.status_code == 200
        user_id = app.state.db.rows('SELECT id FROM users')[0]['id']
        drop_open(app.state.settings.ledger_root / user_id, 'Expenses:Food:Dining')

        replay = client.get('/sessions/gone/runs', headers=headers)
        assert replay.status_code == 200
        record_run, query_run, healthy_run = replay.json()['runs']
        record = record_run['pending_writes'][0]
        assert record['status'] == 'pending'
        assert record.get('receipt') is None
        assert 'Expenses:Food:Dining' in record['preview_error']
        assert query_run['intent'] == 'query'
        assert query_run['steps'][-1]['kicker'] == 'REPLY'
        healthy = healthy_run['pending_writes'][0]
        assert 'preview_error' not in healthy
        assert 'Expenses:Transport' in healthy['receipt']['text']
        assert client.post(f"/chat/pending/{record['id']}/confirm", headers=headers).status_code >= 400


def test_replay_still_opens_when_the_ledger_cannot_load(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        register(client)
    with TestClient(app) as client:
        token = client.post('/auth/login', json={'username': 'mark', 'password': 'correct-horse'}).json()
        headers = {'Authorization': f"Bearer {token['access_token']}"}
        converse(client, headers, 'broken', '火锅128')
        converse(client, headers, 'broken', '微信')
        user_id = app.state.db.rows('SELECT id FROM users')[0]['id']
    root = app.state.settings.ledger_root / user_id
    year = datetime.now().year
    (root / str(year) / 'broken.bean').write_text(
        f'{year}-01-02 * "手改" ""\n  Assets:WeChat:Balance  -10.00 CNY\n  Expenses:Food:Dining  12.00 CNY\n',
        encoding='utf-8',
    )

    fresh = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(fresh) as client:
        replay = client.get('/sessions/broken/runs', headers=headers)
        assert replay.status_code == 200
        record = replay.json()['runs'][0]['pending_writes'][0]
        assert record['status'] == 'pending'
        assert record.get('receipt') is None
        assert '账本无法加载' in record['preview_error']
        assert replay.json()['runs'][0]['steps']
        assert client.post(f"/chat/pending/{record['id']}/confirm", headers=headers).status_code >= 400
