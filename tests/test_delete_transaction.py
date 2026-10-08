"""删除交易会重写账本原文，这是纯追加写入之外的唯一例外（ADR 0013）。"""
from datetime import date
from decimal import Decimal
import subprocess
from uuid import uuid4

import pytest
from beancount import loader

from beanbot.exceptions import DomainError, LedgerWriteConflict, NotFound
from beanbot.gateways.ledger import (
    LedgerFactory, TransactionInput, decode_transaction_id, encode_transaction_id,
)
from tests.test_api import settings


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def ledger_for(tmp_path):
    return LedgerFactory(settings(tmp_path)).get({'id': uuid4().hex, 'ledger_path': None})


def transaction(payee='火锅店', amount='128', day=9):
    return TransactionInput(amount=Decimal(amount), date=date(2026, 9, day), payee=payee, narration='午饭',
                            from_account='Assets:WeChat:Balance', to_account='Expenses:Food:Dining')


async def test_delete_removes_the_entry_and_leaves_the_rest_parseable(tmp_path):
    ledger = ledger_for(tmp_path)
    await ledger.insert([transaction('一号', day=1), transaction('二号', day=2), transaction('三号', day=3)],
                        today=date(2026, 9, 3))
    target = next(item for item in ledger.transactions if item.payee == '二号')

    receipt = await ledger.delete(ledger.transaction_id(target))

    assert receipt['file'] == '2026/09-expenses.bean'
    assert '二号' in receipt['text']
    assert [item.payee for item in ledger.transactions] == ['一号', '三号']
    body = (ledger.root / '2026' / '09-expenses.bean').read_text()
    assert '二号' not in body
    assert '\n\n\n' not in body and body.endswith('\n')
    assert not loader.load_file(str(ledger.root / 'main.bean'))[1]
    assert git(ledger.root, 'show', '-s', '--format=%s', receipt['commit']).startswith('BeanChat: delete')


async def test_deleting_the_only_transaction_leaves_an_empty_file(tmp_path):
    ledger = ledger_for(tmp_path)
    await ledger.insert([transaction()], today=date(2026, 9, 9))

    await ledger.delete(ledger.transaction_id(ledger.transactions[0]))

    assert ledger.transactions == []
    assert (ledger.root / '2026' / '09-expenses.bean').read_text() == ''
    assert not loader.load_file(str(ledger.root / 'main.bean'))[1]


async def test_delete_is_undone_through_the_existing_git_revert_path(tmp_path):
    ledger = ledger_for(tmp_path)
    await ledger.insert([transaction()], today=date(2026, 9, 9))
    receipt = await ledger.delete(ledger.transaction_id(ledger.transactions[0]))

    await ledger.undo(receipt['commit'])

    assert [item.payee for item in ledger.transactions] == ['火锅店']


async def test_a_stale_id_is_refused_instead_of_deleting_the_neighbour(tmp_path):
    ledger = ledger_for(tmp_path)
    await ledger.insert([transaction('一号', day=1), transaction('二号', day=2)], today=date(2026, 9, 2))
    stale = ledger.transaction_id(next(item for item in ledger.transactions if item.payee == '二号'))
    await ledger.delete(ledger.transaction_id(next(item for item in ledger.transactions if item.payee == '一号')))

    # 一号没了之后行号全变了，旧 id 必须被拒绝，而不是删掉挪上来的那一笔
    with pytest.raises(DomainError):
        await ledger.delete(stale)
    assert [item.payee for item in ledger.transactions] == ['二号']


async def test_an_id_whose_digest_no_longer_matches_is_a_conflict(tmp_path):
    ledger = ledger_for(tmp_path)
    await ledger.insert([transaction()], today=date(2026, 9, 9))
    relative, lineno, _ = decode_transaction_id(ledger.transaction_id(ledger.transactions[0]))

    with pytest.raises(LedgerWriteConflict, match='已经变了'):
        await ledger.delete(encode_transaction_id(relative, lineno, 'deadbeef'))
    assert len(ledger.transactions) == 1


async def test_ids_are_rejected_when_they_point_outside_the_ledger(tmp_path):
    ledger = ledger_for(tmp_path)
    await ledger.insert([transaction()], today=date(2026, 9, 9))
    escaping = ledger.transaction_id(ledger.transactions[0])
    relative, lineno, digest = decode_transaction_id(escaping)
    assert relative == '2026/09-expenses.bean'

    import base64
    outside = base64.urlsafe_b64encode(f'../../../etc/passwd:{lineno}:{digest}'.encode()).decode().rstrip('=')
    with pytest.raises(NotFound):
        await ledger.delete(outside)
    with pytest.raises(NotFound):
        await ledger.delete('not-a-real-id')
    assert len(ledger.transactions) == 1


async def test_transaction_source_returns_the_lines_the_dialog_will_show(tmp_path):
    ledger = ledger_for(tmp_path)
    await ledger.insert([transaction()], today=date(2026, 9, 9))

    source = ledger.transaction_source(ledger.transaction_id(ledger.transactions[0]))

    assert source['file'] == '2026/09-expenses.bean'
    assert source['text'].splitlines()[0] == '2026-09-09 * "火锅店" "午饭"'
    assert source['end_line'] - source['start_line'] + 1 == len(source['text'].splitlines())
