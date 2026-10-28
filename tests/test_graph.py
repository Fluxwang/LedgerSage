from datetime import date
from decimal import Decimal
import subprocess
import pytest
from uuid import uuid4

from beanbot.gateways.ledger import LedgerFactory, TransactionInput
from beanbot.services.agent.classify import Classification
from beanbot.services.agent.graph import AgentGraph
from beanbot.services.agent.model import BudgetPlan, ExtractBatch, QueryPlan
from beanbot.services.agent.query import TransactionQuery
from beanbot.services.agent.extract import ExtractedTransaction
from beanbot.services.chat_service import ChatService
from beanbot.services.pending_service import PendingWriteService
from beanbot.storage.database import Database, now
from tests.test_api import settings


async def confirm_all(database, ledgers, user, events):
    """把一次运行产出的待确认写入全部落盘（ADR 0012）。"""
    service = PendingWriteService(database, ledgers)
    return [
        await service.confirm(user, event['pending_id'])
        for event in events
        if event['type'] == 'receipt' and event.get('pending_id')
    ]


class FixtureModel:
    async def classify(self, message, history):
        return Classification(intent='record', confidence=0.95)

    async def extract(self, message, accounts, examples, today):
        return ExtractBatch(transactions=[ExtractedTransaction(
            amount=Decimal('128'), date=date(2026, 9, 9), payee='火锅店', narration='午饭',
            from_account=None, to_account='Expenses:Food:Dining',
        )])

    async def query(self, message, accounts, today):
        return QueryPlan(tool='list_accounts')

    async def budget(self, message, accounts):
        return BudgetPlan(account='Expenses:Food:Dining', amount=Decimal('2000'))


class QueryFixtureModel(FixtureModel):
    async def classify(self, message, history):
        return Classification(intent='query', confidence=0.96)

    async def query(self, message, accounts, today):
        return QueryPlan(tool='query_transactions', arguments=TransactionQuery(
            start=date(2026, 9, 1), end=date(2026, 9, 9), account_prefix='Expenses:', limit=100,
        ))


async def test_salary_asks_for_destination_once_and_confirms_income(tmp_path):
    from tests.test_pending_writes import prepared

    class SalaryModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal('5000'), date=date(2026, 9, 9), payee='公司',
                from_account='Income:Salary',
            )])

    database, user, ledgers = prepared(tmp_path)
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, SalaryModel()), 'fixture')
    events = [event async for event in service.stream(user, 'salary', '今天发工资5000')]
    assert sum(event.get('node') == 'classify' for event in events) == 1
    assert '流入' in events[-1]['question']
    assert '微信' in events[-1]['candidates']
    events = [event async for event in service.stream(user, 'salary', '微信')]
    receipts = await confirm_all(database, ledgers, user, events)
    assert 'Income:Salary -5000 CNY' in ' '.join(receipts[0]['entries'][0].split())
    assert 'Assets:WeChat:Balance' in receipts[0]['entries'][0]


async def test_both_accounts_autofill_from_income_history(tmp_path):
    from tests.test_pending_writes import prepared

    class SalaryModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal('5000'), date=date(2026, 9, 9), payee='公司',
            )])

    database, user, ledgers = prepared(tmp_path)
    await ledgers.get(user).insert([TransactionInput(
        amount=Decimal('5000'), date=date(2026, 9, 1), payee='公司',
        from_account='Income:Salary', to_account='Assets:WeChat:Balance',
    )])
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, SalaryModel()), 'fixture')
    events = [event async for event in service.stream(user, 'salary', '公司发工资5000')]
    assert not any(event['type'] == 'ask' for event in events), events
    receipt = next(event for event in events if event['type'] == 'receipt')
    assert receipt['transactions'][0]['autofilled'] == ['from_account', 'to_account']
    assert 'Income:Salary' in receipt['text']


async def test_ambiguous_account_answer_asks_again_without_losing_other_side(tmp_path):
    from tests.test_pending_writes import prepared

    database, user, ledgers = prepared(tmp_path)
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, FixtureModel()), 'fixture')
    first = [event async for event in service.stream(user, 'ambiguous', '火锅128')]
    assert first[-1]['type'] == 'ask'
    ambiguous = [event async for event in service.stream(user, 'ambiguous', 'Assets:')]
    assert ambiguous[-1]['type'] == 'ask'
    assert '多个' in ambiguous[-1]['question']
    assert set(ambiguous[-1]['candidates']) == {'现金', '微信', '支付宝', '银行卡A'}
    missed = [event async for event in service.stream(user, 'ambiguous', '不存在')]
    assert '没有匹配' in missed[-1]['question']
    final = [event async for event in service.stream(user, 'ambiguous', '微信')]
    receipt = next(event for event in final if event['type'] == 'receipt')
    assert 'Expenses:Food:Dining' in receipt['text']


async def test_exact_display_name_can_resolve_overlapping_names(tmp_path):
    from tests.test_pending_writes import prepared

    database, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)
    with (ledger.root / 'accounts/assets.bean').open('a') as stream:
        stream.write('\n1970-01-01 open Assets:WeChat:Wallet\n  name: "微信零钱"\n')
    ledger.reload()
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, FixtureModel()), 'fixture')
    first = [event async for event in service.stream(user, 'names', '火锅128')]
    assert '微信' in first[-1]['candidates']
    final = [event async for event in service.stream(user, 'names', '微信')]
    assert any(event['type'] == 'receipt' for event in final)


async def test_split_salary_is_explicitly_refused(tmp_path):
    from tests.test_pending_writes import prepared

    database, user, ledgers = prepared(tmp_path)
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, FixtureModel()), 'fixture')
    events = [event async for event in service.stream(user, 'split', '工资8000，扣五险一金1000，到手7000')]
    assert not any(event['type'] == 'receipt' for event in events)
    assert '手写' in events[-1].get('question', '') or any('手写' in event.get('content', '') for event in events)


async def test_dated_deduction_and_independent_transactions_are_not_split_postings(tmp_path):
    from tests.test_pending_writes import prepared

    class BatchModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal(amount), date=date(2026, 9, 9), payee=payee,
                from_account='Assets:Cash', to_account='Expenses:Other',
            ) for amount, payee in [('10', '运营商'), ('20', '餐馆')]])

    database, user, ledgers = prepared(tmp_path)
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, BatchModel()), 'fixture')
    events = [event async for event in service.stream(user, 'batch', '2026-09-09扣话费10；另外餐馆吃饭20')]
    receipt = next(event for event in events if event['type'] == 'receipt')
    assert len(receipt['entries']) == 2


@pytest.mark.parametrize('source,target,answer,expected_source,expected_target', [
    ('Assets:Alipay:Balance', None, '微信', 'Assets:Alipay:Balance', 'Assets:WeChat:Balance'),
    ('Assets:Alipay:Balance', None, '信用卡', 'Assets:Alipay:Balance', 'Liabilities:CreditCard'),
    ('Assets:Cash', 'Income:Salary', None, 'Income:Salary', 'Assets:Cash'),
])
async def test_transfer_and_reversed_income_reach_ledger(tmp_path, source, target, answer, expected_source, expected_target):
    from tests.test_pending_writes import prepared

    class FlowModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal('300'), date=date(2026, 9, 9), payee='资金流动',
                from_account=source, to_account=target,
            )])

    database, user, ledgers = prepared(tmp_path)
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, FlowModel()), 'fixture')
    events = [event async for event in service.stream(user, 'flow', '转300')]
    if answer:
        assert answer in events[-1]['candidates']
        assert '期初余额' not in events[-1]['candidates']
        events = [event async for event in service.stream(user, 'flow', answer)]
    await confirm_all(database, ledgers, user, events)
    postings = ledgers.get(user).transactions[0].postings
    assert [(p.account, p.units.number) for p in postings] == [(expected_source, Decimal('-300')), (expected_target, Decimal('300'))]


async def test_low_confidence_only_asks_uncertain_side_and_preserves_explicit_account(tmp_path):
    from tests.test_pending_writes import prepared

    class CashModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal('100'), date=date(2026, 9, 9), payee='商店',
                from_account='Assets:Cash' if '现金' in message else None,
            )])

    database, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)
    for target in ('Expenses:Food:Dining', 'Expenses:Other'):
        await ledger.insert([TransactionInput(amount=Decimal('100'), date=date(2026, 9, 1), payee='商店',
                                             from_account='Assets:WeChat:Balance', to_account=target)])
    config = settings(tmp_path).model_copy(update={'clarification_candidate_limit': 2})
    service = ChatService(database, AgentGraph(config, database, ledgers, CashModel()), 'fixture')
    for thread, message, expected in [('auto', '商店100', 'Assets:WeChat:Balance'), ('explicit', '商店现金100', 'Assets:Cash')]:
        events = [event async for event in service.stream(user, thread, message)]
        assert '流入' in events[-1]['question']
        assert len(events[-1]['candidates']) == 2
        events = [event async for event in service.stream(user, thread, '餐饮')]
        receipt = next(event for event in events if event['type'] == 'receipt')
        assert receipt['transactions'][0]['from_account'] == expected


async def test_extract_passes_the_runtime_date_to_the_model(tmp_path):
    class DateRecordingModel(FixtureModel):
        received_today = None

        async def extract(self, message, accounts, examples, today):
            self.received_today = today
            return await super().extract(message, accounts, examples, today)

    config = settings(tmp_path)
    database = Database(config.database_path)
    user = {'id': uuid4().hex, 'username': 'mark', 'ledger_path': None}
    database.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                     (user['id'], user['username'], 'unused', None, now()))
    ledgers = LedgerFactory(config)
    model = DateRecordingModel()
    graph = AgentGraph(config, database, ledgers, model)

    await graph.extract({'user': user, 'message': '昨天的地铁6块'})

    assert model.received_today == date.today()


async def test_explicit_accounts_do_not_need_merchant_history(tmp_path):
    from tests.test_pending_writes import prepared

    class ExplicitModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal('68'), date=date(2026, 9, 9), payee='新商户',
                from_account='Assets:WeChat:Balance', to_account='Expenses:Food:Dining',
            )])

    database, user, ledgers = prepared(tmp_path)
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, ExplicitModel()), 'fixture')
    events = [event async for event in service.stream(user, 'explicit', '微信在新商户吃饭68')]
    assert not any(event['type'] == 'ask' for event in events)
    receipt = next(event for event in events if event['type'] == 'receipt')
    assert receipt['transactions'][0]['from_account'] == 'Assets:WeChat:Balance'
    assert receipt['transactions'][0]['autofilled'] == []


async def test_clarification_resumes_the_same_run_and_writes_after_confirm(tmp_path):
    config = settings(tmp_path)
    database = Database(config.database_path)
    user = {'id': uuid4().hex, 'username': 'mark', 'ledger_path': None}
    database.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                     (user['id'], user['username'], 'unused', None, now()))
    ledgers = LedgerFactory(config)
    service = ChatService(database, AgentGraph(config, database, ledgers, FixtureModel()), 'fixture')

    first = [event async for event in service.stream(user, 'thread-1', '火锅128')]
    assert first[-1]['type'] == 'ask'
    run_id = first[-1]['run_id']
    second = [event async for event in service.stream(user, 'thread-1', '微信')]
    receipts = [event for event in second if event['type'] == 'receipt']
    assert all(event['run_id'] == run_id for event in second)
    assert len(database.rows('SELECT * FROM runs')) == 1
    assert any(step['kicker'] == 'ASK' for step in database.steps(run_id))

    # 预览阶段账本一个字节都没动
    assert receipts[0]['pending_id']
    assert receipts[0]['entries'][0].startswith('2026-09-09 * "火锅店"')
    assert ledgers.get(user).transactions == []

    await confirm_all(database, ledgers, user, second)
    assert len(ledgers.get(user).transactions) == 1
    stored = database.rows('SELECT status,commit_sha FROM pending_writes')[0]
    assert stored['status'] == 'confirmed' and stored['commit_sha']


async def test_query_branch_returns_verifiable_numbers_without_writing(tmp_path):
    config = settings(tmp_path)
    database = Database(config.database_path)
    user = {'id': uuid4().hex, 'username': 'mark', 'ledger_path': None}
    database.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                     (user['id'], user['username'], 'unused', None, now()))
    ledgers = LedgerFactory(config)
    ledger = ledgers.get(user)
    await ledger.insert([TransactionInput(
        amount=Decimal('128'), date=date(2026, 9, 9), payee='火锅店', narration='午饭',
        from_account='Assets:WeChat:Balance', to_account='Expenses:Food:Dining',
    )])
    before = subprocess.check_output(['git', '-C', str(ledger.root), 'rev-parse', 'HEAD'], text=True).strip()
    service = ChatService(database, AgentGraph(config, database, ledgers, QueryFixtureModel()), 'fixture')

    events = [event async for event in service.stream(user, 'query-thread', '这个月餐饮花了多少')]

    messages = [event['content'] for event in events if event['type'] == 'message']
    assert messages == ['2026-09-01 至 2026-09-09，Expenses 共 1 笔，支出合计 128.00。']
    assert len(ledger.query_transactions(date(2026, 9, 1), date(2026, 9, 9), 'Expenses:')) == 1
    after = subprocess.check_output(['git', '-C', str(ledger.root), 'rev-parse', 'HEAD'], text=True).strip()
    assert after == before


@pytest.mark.parametrize('from_account,to_account,expected', [
    (None, 'Expenses:Food:Dining', '记录火锅店支出'),
    ('Income:Salary', 'Assets:WeChat:Balance', '记录火锅店收入'),
    ('Assets:Cash', 'Assets:WeChat:Balance', '记录火锅店转账'),
    (None, None, '记录火锅店交易'),
])
def test_run_title_names_the_direction(tmp_path, from_account, to_account, expected):
    """收入与转账的运行不该在历史列表里被叫作「支出」。"""
    from tests.test_pending_writes import prepared

    database, user, ledgers = prepared(tmp_path)
    graph = AgentGraph(settings(tmp_path), database, ledgers, FixtureModel())
    state = {'intent': 'record', 'transactions': [
        {'payee': '火锅店', 'from_account': from_account, 'to_account': to_account},
    ]}
    assert graph.run_title(state) == expected


def test_reply_names_the_largest_transaction_when_ordered_by_amount():
    plan = QueryPlan(tool='query_transactions', arguments=TransactionQuery(
        start=date(2026, 9, 1), end=date(2026, 9, 9), order_by='amount_desc', limit=1,
    ))
    rows = [{'date': '2026-09-05', 'payee': '山姆会员店', 'narration': '周末采购', 'amount': '209.00', 'postings': []}]
    assert AgentGraph._query_reply(rows, plan) == '2026-09-01 至 2026-09-09，金额最大的一笔是 2026-09-05 山姆会员店 · 周末采购，209.00。'


def open_parent_food(ledgers, user):
    """补开汇总账户 Expenses:Food，它下面已有 Expenses:Food:Dining 等末级账户（ADR 0016）。"""
    ledger = ledgers.get(user)
    with (ledger.root / 'accounts/expenses.bean').open('a') as stream:
        stream.write('\n1970-01-01 open Expenses:Food\n  name: "饮食"\n')
    ledger.reload()
    return ledger


async def test_parent_account_is_not_offered_as_a_candidate(tmp_path):
    from tests.test_pending_writes import prepared

    class UnknownTargetModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            self.accounts = [account for account, _ in accounts]
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal('30'), date=date(2026, 9, 9), payee='便利店',
                from_account='Assets:WeChat:Balance', to_account=None,
            )])

    database, user, ledgers = prepared(tmp_path)
    open_parent_food(ledgers, user)
    model = UnknownTargetModel()
    config = settings(tmp_path)
    config.clarification_candidate_limit = 100
    service = ChatService(database, AgentGraph(config, database, ledgers, model), 'fixture')
    events = [event async for event in service.stream(user, 'parent', '买了点吃的30')]
    assert 'Expenses:Food' not in model.accounts
    assert events[-1]['type'] == 'ask'
    assert '饮食' not in events[-1]['candidates']
    assert '餐饮' in events[-1]['candidates']


async def test_parent_account_from_model_is_refused_with_reason(tmp_path):
    from tests.test_pending_writes import prepared

    class ParentModel(FixtureModel):
        async def extract(self, message, accounts, examples, today):
            return ExtractBatch(transactions=[ExtractedTransaction(
                amount=Decimal('30'), date=date(2026, 9, 9), payee='便利店',
                from_account='Assets:WeChat:Balance', to_account='Expenses:Food',
            )])

    database, user, ledgers = prepared(tmp_path)
    open_parent_food(ledgers, user)
    service = ChatService(database, AgentGraph(settings(tmp_path), database, ledgers, ParentModel()), 'fixture')
    events = [event async for event in service.stream(user, 'parent', '买了点吃的30')]
    assert not any(event['type'] == 'receipt' for event in events)
    assert events[-1]['type'] == 'ask'
    assert '汇总账户' in events[-1]['question']


async def test_confirm_revalidates_and_refuses_parent_account(tmp_path):
    from beanbot.exceptions import LedgerWriteConflict
    from tests.test_pending_writes import prepared, transaction

    database, user, ledgers = prepared(tmp_path)
    payload = transaction().model_dump(mode='json') | {'to_account': 'Expenses:Food'}
    pending = database.create_pending(user['id'], None, 'record', {'transactions': [payload]})
    open_parent_food(ledgers, user)
    with pytest.raises(LedgerWriteConflict, match='汇总账户'):
        await PendingWriteService(database, ledgers).confirm(user, pending['id'])
    assert ledgers.get(user).transactions == []
