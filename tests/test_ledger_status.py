"""账本健康度读取磁盘，不依赖账本工厂能否加载或其缓存。"""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.gateways.ledger.repo import git, scaffold_ledger
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_graph import FixtureModel


def prepared(tmp_path):
    app = create_app(settings(tmp_path), agent_model=FixtureModel())
    client = TestClient(app)
    headers = register(client)
    user = app.state.db.rows('SELECT id,ledger_path FROM users')[0]
    root = app.state.ledgers.get(user).root
    return app, client, headers, root


def test_clean_status_and_head_commit_time(tmp_path):
    _, client, headers, root = prepared(tmp_path)
    with client:
        assert client.get('/ledger/status').status_code == 401
        response = client.get('/ledger/status', headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['bean_check'] == {'ok': True, 'error_count': 0, 'message': 'bean-check 通过'}
    assert body['git'] == {'clean': True, 'last_commit_at': git(root, 'show', '-s', '--format=%cI', 'HEAD')}
    assert [item['key'] for item in body['health']] == ['bean_check', 'working_tree', 'missing_payee']
    assert all(item['level'] == 'ok' for item in body['health'])


def test_manual_edit_is_checked_again_and_reports_relative_location(tmp_path):
    _, client, headers, root = prepared(tmp_path)
    target = root / str(date.today().year) / 'manual.bean'
    with client:
        assert client.get('/ledger/status', headers=headers).json()['bean_check']['ok']
        target.write_text(
            f'{date.today()} * "商店" "不平衡"\n'
            '  Expenses:Other  10 CNY\n  Assets:Cash  -9 CNY\n', encoding='utf-8',
        )
        body = client.get('/ledger/status', headers=headers).json()
        assert body['bean_check']['ok'] is False
        assert body['bean_check']['error_count'] >= 1
        message = body['bean_check']['message']
        assert f'{date.today().year}/manual.bean:1' in message
        assert 'balance' in message
        assert str(root) not in message and root.as_posix() not in message
        assert body['health'][0]['level'] == 'warn'
        target.unlink()
        assert client.get('/ledger/status', headers=headers).json()['bean_check']['ok']


def test_first_load_failure_in_adopted_ledger_still_returns_status(tmp_path):
    app, client, headers, _ = prepared(tmp_path)
    adopted = tmp_path / '手工账本'
    scaffold_ledger(adopted)
    (adopted / 'main.bean').write_text('include "missing.bean"\n', encoding='utf-8')
    with app.state.db.connect() as db:
        db.execute('UPDATE users SET ledger_path=?', (str(adopted),))
    # 新应用没有加载过此账本；普通工厂会拒绝它。
    fresh = create_app(settings(tmp_path), agent_model=FixtureModel())
    with TestClient(fresh) as other:
        assert other.get('/dashboard', headers=headers).status_code == 409
        response = other.get('/ledger/status', headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['bean_check']['ok'] is False
    assert 'missing.bean' in body['bean_check']['message']
    assert str(adopted) not in body['bean_check']['message']
    assert adopted.as_posix() not in body['bean_check']['message']


def test_git_ignores_untracked_text_but_counts_new_bean_and_tracked_changes(tmp_path):
    _, client, headers, root = prepared(tmp_path)
    with client:
        (root / 'foo.txt').write_text('编辑器笔记', encoding='utf-8')
        assert client.get('/ledger/status', headers=headers).json()['git']['clean'] is True
        new = root / '新账本.bean'
        new.write_text('; 尚未纳入版本管理', encoding='utf-8')
        body = client.get('/ledger/status', headers=headers).json()
        assert body['git']['clean'] is False
        assert body['health'][1]['level'] == 'warn'
        new.unlink()
        main = root / 'main.bean'
        main.write_text(main.read_text(encoding='utf-8') + '\n; 手工修改\n', encoding='utf-8')
        assert client.get('/ledger/status', headers=headers).json()['git']['clean'] is False
        git(root, 'add', 'main.bean')
        assert client.get('/ledger/status', headers=headers).json()['git']['clean'] is False


def test_missing_payee_counts_all_expenses_but_not_transfers_income_or_refunds(tmp_path):
    _, client, headers, root = prepared(tmp_path)
    target = root / str(date.today().year) / 'manual.bean'
    old = date.today() - timedelta(days=400)
    target.write_text(''.join(
        f'{day} * "" "测试"\n  {to}  10 CNY\n  {source}  -10 CNY\n\n'
        for day, source, to in [
            (old, 'Assets:Cash', 'Expenses:Other'),
            (date.today(), 'Assets:Cash', 'Expenses:Food:Dining'),
            (date.today(), 'Assets:Cash', 'Assets:WeChat:Balance'),
            (date.today(), 'Income:Salary', 'Assets:Cash'),
            (date.today(), 'Expenses:Other', 'Assets:Cash'),
        ]
    ), encoding='utf-8')
    with client:
        body = client.get('/ledger/status', headers=headers).json()
    missing = next(item for item in body['health'] if item['key'] == 'missing_payee')
    assert missing == {'key': 'missing_payee', 'level': 'warn', 'text': '2 笔支出缺收款方'}


def test_status_is_scoped_to_current_user(tmp_path):
    app, client, headers, root = prepared(tmp_path)
    (root / 'new.bean').write_text('; 未提交', encoding='utf-8')
    app.state.db.invite('second-invite')
    with client:
        response = client.post('/auth/register', json={
            'username': 'second', 'password': 'correct-horse', 'invite_code': 'second-invite',
        })
        second = {'Authorization': f"Bearer {response.json()['access_token']}"}
        assert client.get('/ledger/status', headers=headers).json()['git']['clean'] is False
        assert client.get('/ledger/status', headers=second).json()['git']['clean'] is True


def test_uninitialized_adopted_ledger_is_checked_without_creating_files(tmp_path):
    app, client, headers, _ = prepared(tmp_path)
    adopted = tmp_path / '未初始化账本'
    adopted.mkdir()
    (adopted / 'main.bean').write_text('include "nested/missing.bean"\n', encoding='utf-8')
    with app.state.db.connect() as db:
        db.execute('UPDATE users SET ledger_path=?', (str(adopted),))
    with client:
        response = client.get('/ledger/status', headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['bean_check']['ok'] is False
    assert 'nested/missing.bean' in body['bean_check']['message']
    assert body['git'] == {'clean': False, 'last_commit_at': None}
    assert sorted(path.name for path in adopted.iterdir()) == ['main.bean']


def test_missing_main_file_still_returns_health(tmp_path):
    _, client, headers, root = prepared(tmp_path)
    (root / 'main.bean').unlink()
    with client:
        response = client.get('/ledger/status', headers=headers)
    assert response.status_code == 200
    assert response.json()['bean_check']['ok'] is False
    assert str(root) not in response.json()['bean_check']['message']
