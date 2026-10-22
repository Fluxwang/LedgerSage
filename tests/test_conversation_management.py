"""通过 HTTP 验证对话改名、软删除和保留的审计记录。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from beanbot.api.app import create_app
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_runs import RoutingFixtureModel, converse


def test_rename_trims_validates_and_survives_further_messages(tmp_path):
    config = settings(tmp_path)
    # 验证配置确实生效，而不是在端点中写死上限。
    config = config.model_copy(update={'conversation_title_max_length': 6})
    app = create_app(config, agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'rename', '这个月花了多少')
        response = client.patch('/sessions/rename', headers=headers, json={'title': '  我的账本  '})
        assert response.status_code == 200
        assert response.json() == {'thread_id': 'rename', 'title': '我的账本'}
        for title in ['', '   ', '\n\t', '超过六个字的标题']:
            invalid = client.patch('/sessions/rename', headers=headers, json={'title': title})
            assert invalid.status_code == 422
            assert isinstance(invalid.json()['detail'], str)
            assert client.get('/sessions', headers=headers).json()[0]['title'] == '我的账本'
        assert client.patch('/sessions/rename', headers=headers, json={}).status_code == 422
        assert client.patch('/sessions/rename', headers=headers, json={'title': None}).status_code == 422
        converse(client, headers, 'rename', '今年花了多少')
        assert client.get('/sessions', headers=headers).json()[0]['title'] == '我的账本'
        assert client.patch('/sessions/rename', headers=headers, json={'title': '六个字的标题'}).status_code == 200


def test_automatic_title_uses_config_without_changing_existing_titles(tmp_path):
    config = settings(tmp_path)
    app = create_app(config, agent_model=RoutingFixtureModel())
    message = '请帮我看看这个月总共花了多少'
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'old', message)
        assert client.get('/sessions', headers=headers).json()[0]['title'] == message[:10]
    shorter = create_app(config.model_copy(update={'conversation_title_auto_length': 4}), agent_model=RoutingFixtureModel())
    with TestClient(shorter) as client:
        converse(client, headers, 'new', message)
        converse(client, headers, 'old', message)
        titles = {row['thread_id']: row['title'] for row in client.get('/sessions', headers=headers).json()}
        assert titles == {'old': message[:10], 'new': message[:4]}
    for name in ['conversation_title_max_length', 'conversation_title_auto_length']:
        for value in [0, 201]:
            with pytest.raises(ValidationError):
                type(config)(_env_file=None, **(config.model_dump() | {name: value}))


def test_management_rejects_foreign_missing_and_unauthenticated_requests(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'private', '这个月花了多少')
        app.state.db.invite('other-invite')
        other = client.post('/auth/register', json={
            'username': 'other', 'password': 'correct-horse', 'invite_code': 'other-invite',
        }).json()
        foreign = {'Authorization': f"Bearer {other['access_token']}"}
        for auth, thread in [(foreign, 'private'), (headers, 'missing')]:
            assert client.patch(f'/sessions/{thread}', headers=auth, json={'title': '新标题'}).status_code == 404
            assert client.delete(f'/sessions/{thread}', headers=auth).status_code == 404
        assert client.patch('/sessions/private', json={'title': '新标题'}).status_code == 401
        assert client.delete('/sessions/private').status_code == 401
        assert len(client.get('/sessions', headers=headers).json()) == 1


def pending_record(client, headers, thread):
    events = converse(client, headers, thread, '火锅128')
    if events[-1]['type'] == 'ask':
        events = converse(client, headers, thread, '微信')
    return next(event['pending_id'] for event in events if event['type'] == 'receipt')


def test_delete_rejects_all_pending_and_preserves_ledger_saved_queries_and_audit(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        confirmed = pending_record(client, headers, 'delete')
        assert client.post(f'/chat/pending/{confirmed}/confirm', headers=headers).status_code == 200
        query = converse(client, headers, 'delete', '这个月花了多少')
        saved = client.post('/saved-queries', headers=headers, json={'run_id': query[-1]['run_id']}).json()
        pending = pending_record(client, headers, 'delete')
        stale = pending_record(client, headers, 'delete')
        earlier = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        app.state.db.execute('UPDATE pending_writes SET created_at=? WHERE id=?', (earlier, stale))
        untouched = pending_record(client, headers, 'keep')
        session = next(row for row in client.get('/sessions', headers=headers).json() if row['thread_id'] == 'delete')
        assert session['pending_write_count'] == 1
        user = app.state.db.rows('SELECT id,ledger_path FROM users')[0]
        ledger = app.state.ledgers.get(user)
        files_before = {path.relative_to(ledger.root): path.read_bytes() for path in ledger.root.rglob('*.bean')}
        head_before = client.get('/ledger/status', headers=headers).json()['git']['last_commit_at']
        counts_before = {table: len(app.state.db.rows(f'SELECT * FROM {table}')) for table in ['runs', 'run_steps', 'pending_writes', 'saved_queries']}
        checkpoint_tables = [row['name'] for row in app.state.db.rows(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('checkpoints','writes')"
        )]
        assert 'checkpoints' in checkpoint_tables
        checkpoints_before = {table: app.state.db.rows(f'SELECT * FROM {table}') for table in checkpoint_tables}

        deleted = client.delete('/sessions/delete', headers=headers)
        assert deleted.status_code == 204 and deleted.content == b''
        assert [row['thread_id'] for row in client.get('/sessions', headers=headers).json()] == ['keep']
        assert client.get('/sessions/delete/runs', headers=headers).status_code == 404
        assert client.patch('/sessions/delete', headers=headers, json={'title': '复活'}).status_code == 404
        assert client.delete('/sessions/delete', headers=headers).status_code == 404
        assert client.post('/chat/stream', headers=headers, json={'thread_id': 'delete', 'message': '这个月花了多少'}).status_code == 404
        for pending_id in [pending, stale]:
            record = app.state.db.rows('SELECT * FROM pending_writes WHERE id=?', (pending_id,))[0]
            assert record['status'] == 'rejected' and record['resolved_at']
            assert client.post(f'/chat/pending/{pending_id}/confirm', headers=headers).status_code == 409
        assert app.state.db.pending(confirmed, user['id'])['status'] == 'confirmed'
        assert app.state.db.pending(confirmed, user['id'])['commit_sha']
        assert app.state.db.pending(untouched, user['id'])['status'] == 'pending'
        assert client.get('/saved-queries', headers=headers).json() == [saved]
        assert client.get('/runs/' + query[-1]['run_id'], headers=headers).status_code == 200
        assert client.get('/transactions', headers=headers).json()['total'] == 1
        assert client.get('/ledger/status', headers=headers).json()['git']['last_commit_at'] == head_before
        assert {path.relative_to(ledger.root): path.read_bytes() for path in ledger.root.rglob('*.bean')} == files_before
        assert {table: len(app.state.db.rows(f'SELECT * FROM {table}')) for table in counts_before} == counts_before
        assert {table: app.state.db.rows(f'SELECT * FROM {table}') for table in checkpoint_tables} == checkpoints_before


def test_delete_pending_clarification_cannot_resume_it(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, 'ask', '火锅128')
        assert client.get('/sessions', headers=headers).json()[0]['has_pending_ask']
        assert client.get('/sessions', headers=headers).json()[0]['pending_write_count'] == 0
        assert client.delete('/sessions/ask', headers=headers).status_code == 204
        assert client.post('/chat/stream', headers=headers, json={'thread_id': 'ask', 'message': '微信'}).status_code == 404


def test_delete_rolls_back_if_rejecting_pending_writes_fails(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = register(client)
        pending = pending_record(client, headers, 'atomic')
        # 模拟存储层拒绝这次更新，HTTP 失败时两个状态都必须保持原样。
        app.state.db.execute(
            "CREATE TRIGGER reject_failure BEFORE UPDATE OF status ON pending_writes "
            "WHEN NEW.status='rejected' BEGIN SELECT RAISE(ABORT, '模拟写入失败'); END"
        )
        assert client.delete('/sessions/atomic', headers=headers).status_code == 500
        assert client.get('/sessions', headers=headers).json()[0]['thread_id'] == 'atomic'
        assert client.get('/sessions/atomic/runs', headers=headers).status_code == 200
        assert app.state.db.rows('SELECT status FROM pending_writes WHERE id=?', (pending,))[0]['status'] == 'pending'


def test_upgrade_v4_database_preserves_old_conversations_and_can_soft_delete(tmp_path):
    config = settings(tmp_path)
    config.database_path.parent.mkdir(parents=True)
    with sqlite3.connect(config.database_path) as db:
        db.execute('CREATE TABLE schema_version(version INTEGER PRIMARY KEY)')
        for migration in sorted(Path('beanbot/storage/migrations').glob('00[1-4]_*.sql')):
            db.executescript(migration.read_text(encoding='utf-8'))
            db.execute('INSERT INTO schema_version VALUES(?)', (int(migration.stem[:3]),))
        db.execute("INSERT INTO users VALUES('legacy','legacy','unused',NULL,'2026-01-01')")
        db.execute("INSERT INTO sessions VALUES('legacy-session','legacy','old','保留的旧标题','2026-01-01','2026-01-01',NULL,NULL)")
    app = create_app(config, agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        owner = client.get('/auth/me', headers=headers).json()['id']
        app.state.db.execute("UPDATE sessions SET user_id=? WHERE id='legacy-session'", (owner,))
        row = client.get('/sessions', headers=headers).json()[0]
        assert row['title'] == '保留的旧标题' and row['pending_write_count'] == 0
        assert client.delete('/sessions/old', headers=headers).status_code == 204
    fresh = create_app(config, agent_model=RoutingFixtureModel())
    with TestClient(fresh) as client:
        assert client.get('/sessions', headers=headers).json() == []
        assert client.get('/sessions/old/runs', headers=headers).status_code == 404
