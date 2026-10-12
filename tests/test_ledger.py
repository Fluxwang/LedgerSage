import asyncio
from datetime import date
from decimal import Decimal
import subprocess
import pytest
from beancount import loader
from beanbot.gateways.ledger import LedgerFactory, TransactionInput
from beanbot.exceptions import AccountNotFound
from tests.test_api import settings


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def transaction(**kwargs):
    return TransactionInput(amount=Decimal('128'), date=date(2026, 8, 1), payee='火锅店', narration='午饭',
                            from_account='Assets:WeChat:Balance', to_account=kwargs.get('to_account', 'Expenses:Food:Dining'))


@pytest.mark.parametrize('source,target,expected_source,expected_target,direction', [
    ('Assets:Cash', 'Income:Salary', 'Income:Salary', 'Assets:Cash', '收入'),
    ('Expenses:Food:Dining', 'Assets:Cash', 'Expenses:Food:Dining', 'Assets:Cash', '转账'),
    ('Expenses:Food:Dining', 'Income:Salary', 'Income:Salary', 'Expenses:Food:Dining', '支出'),
    ('Assets:Cash', 'Liabilities:CreditCard', 'Assets:Cash', 'Liabilities:CreditCard', '转账'),
])
def test_transaction_normalizes_fund_flow(source, target, expected_source, expected_target, direction):
    item = TransactionInput(amount=Decimal('100'), date=date(2026, 9, 1), payee='测试',
                            from_account=source, to_account=target)
    assert (item.from_account, item.to_account, item.direction) == (expected_source, expected_target, direction)
    with pytest.raises((AttributeError, ValueError)):
        item.direction = '收入'


async def test_atomic_concurrent_write_rollover_and_undo(tmp_path):
    factory = LedgerFactory(settings(tmp_path))
    ledger = factory.get({'id': 'one', 'ledger_path': None})
    original = git(ledger.root, 'rev-list', '--count', 'HEAD')
    (ledger.root / 'notes.txt').write_text('人工编辑')
    git(ledger.root, 'add', 'notes.txt')
    first, second = await asyncio.gather(ledger.insert([transaction()], today=date(2026, 8, 31)),
                                         ledger.insert([transaction()] * 3, today=date(2026, 9, 1)))
    assert first['file'] == '2026/08-expenses.bean'
    assert second['file'] == '2026/09-expenses.bean'
    assert int(git(ledger.root, 'rev-list', '--count', 'HEAD')) == int(original) + 2
    assert git(ledger.root, 'show', '--format=', '--name-only', second['commit']) == second['file']
    assert len(ledger.transactions) == 4
    await ledger.undo(second['commit'])
    assert len(ledger.transactions) == 1
    assert 'notes.txt' in git(ledger.root, 'diff', '--cached', '--name-only')
    assert not loader.load_file(str(ledger.root / 'main.bean'))[1]
    with pytest.raises(AccountNotFound, match='第 2 笔'):
        await ledger.insert([transaction(), transaction(to_account='Expenses:Missing')])
    assert len(ledger.transactions) == 1


async def test_budget_adjustments_are_append_only(tmp_path):
    ledger = LedgerFactory(settings(tmp_path)).get({'id': 'one', 'ledger_path': None})
    await ledger.set_budget('Expenses:Food:Dining', Decimal('2000'), effective_date=date(2026, 8, 1))
    await ledger.set_budget('Expenses:Food:Dining', Decimal('2500'), effective_date=date(2026, 9, 1))
    lines = (ledger.root / 'budgets.bean').read_text().count('custom "budget"')
    assert lines == 2
    assert ledger.budgets() == [{
        'account': 'Expenses:Food:Dining', 'period': 'monthly', 'amount': '2500.00',
        'currency': 'CNY', 'effective_date': '2026-09-01',
    }]
    assert not ledger.errors


async def test_changing_a_budget_period_supersedes_the_old_one(tmp_path):
    """同一账户只有日期最新的那条生效，改周期不该留下两条并行的预算（ADR-0008）。"""
    ledger = LedgerFactory(settings(tmp_path)).get({'id': 'one', 'ledger_path': None})
    await ledger.set_budget('Expenses:Food:Dining', Decimal('2000'), effective_date=date(2026, 8, 1))
    await ledger.set_budget(
        'Expenses:Food:Dining', Decimal('500'), period='weekly', effective_date=date(2026, 9, 1),
    )
    assert (ledger.root / 'budgets.bean').read_text().count('custom "budget"') == 2
    assert [(item['period'], item['amount']) for item in ledger.budgets()] == [('weekly', '500.00')]


def test_transaction_rejects_an_empty_account():
    """空账户名推不出方向，构造期就该挡掉，而不是让它落到「转账」这个兜底上。"""
    with pytest.raises(ValueError):
        TransactionInput(amount=Decimal('100'), date=date(2026, 9, 1), payee='测试',
                         from_account='', to_account='Assets:Cash')
