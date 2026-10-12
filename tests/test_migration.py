import subprocess
import pytest
from beanbot.migrate_account_names import migrate_account_names


def test_open_comment_migration_preserves_commented_lines(tmp_path):
    root = tmp_path / 'ledger'; root.mkdir()
    (root / 'main.bean').write_text('include "accounts.bean"\n')
    (root / 'accounts.bean').write_text(
        '2020-01-01 open Assets:Cash ;现金\n; 2020-01-01 open Assets:Old ;旧账户\n'
        '2020-01-01 open Income:Salary\n'
    )
    subprocess.run(['git', '-C', root, 'init', '-q'], check=True)
    subprocess.run(['git', '-C', root, 'config', 'user.name', 'Test'], check=True)
    subprocess.run(['git', '-C', root, 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', root, 'add', '.'], check=True)
    subprocess.run(['git', '-C', root, 'commit', '-qm', 'initial'], check=True)
    assert migrate_account_names(root) == ['accounts.bean: Assets:Cash → 现金']
    assert (root / 'accounts.bean').read_text() == (
        '2020-01-01 open Assets:Cash\n  name: "现金"\n; 2020-01-01 open Assets:Old ;旧账户\n'
        '2020-01-01 open Income:Salary\n'
    )


def test_migration_manual_names_dry_run_commit_and_idempotence(tmp_path):
    from beanbot.gateways.ledger import scaffold_ledger
    root = tmp_path / 'ledger'
    scaffold_ledger(root)
    path = root / 'accounts' / 'income.bean'
    path.write_text('1970-01-01 open Income:Salary\n')
    subprocess.run(['git', '-C', root, 'commit', '-am', 'remove name'], check=True, capture_output=True)
    before = path.read_bytes()
    names = {'Income:Salary': '工资收入'}
    assert migrate_account_names(root, names, dry_run=True)
    assert path.read_bytes() == before
    assert migrate_account_names(root, names, commit=True)
    assert 'name: "工资收入"' in path.read_text()
    assert subprocess.check_output(['git', '-C', root, 'status', '--porcelain']) == b''
    assert migrate_account_names(root, names) == []


def test_failed_migration_restores_exact_original_bytes(tmp_path, monkeypatch):
    from beanbot.gateways.ledger import scaffold_ledger
    from beanbot import migrate_account_names as migration

    root = tmp_path / 'ledger'
    scaffold_ledger(root)
    path = root / 'accounts' / 'income.bean'
    path.write_bytes(b'1970-01-01 open Income:Salary\r\n')
    subprocess.run(['git', '-C', root, 'commit', '-am', 'remove name'], check=True, capture_output=True)
    original = path.read_bytes()
    load = migration.loader.load_file
    def invalid_after_change(filename):
        entries, errors, options = load(filename)
        return entries, errors if path.read_bytes() == original else ['invalid migration'], options
    monkeypatch.setattr(migration.loader, 'load_file', invalid_after_change)
    with pytest.raises(RuntimeError, match='校验失败'):
        migrate_account_names(root, {'Income:Salary': '工资'})
    assert path.read_bytes() == original
    assert subprocess.check_output(['git', '-C', root, 'status', '--porcelain']) == b''
