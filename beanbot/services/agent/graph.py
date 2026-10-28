"""带 SQLite checkpoint 和 interrupt 的对话运行图。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from difflib import get_close_matches
from time import perf_counter
from typing import Any, AsyncIterator, TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langchain_core.runnables import RunnableConfig

from beanbot.config import Settings
from beanbot.gateways.ledger.accounts import account_matches, normalize_prefix
from beanbot.gateways.ledger import LedgerFactory, TransactionInput, flow_direction
from beanbot.services.agent.classify import Classification, Intent, route_classification
from beanbot.services.agent.confidence import account_confidence
from beanbot.services.agent.accounts import FIELDS, allowed_accounts, candidates, missing_fields, normalize, preview_accounts, role_history
from beanbot.services.agent.extract import extraction_issues, route_after_extract
from beanbot.services.agent.model import AgentModel
from beanbot.storage.database import Database, now
from beanbot.services.vector_index import VectorIndexManager


class AgentState(TypedDict, total=False):
    message: str
    history: list[str]
    user: dict
    run_id: str
    intent: Intent
    confidence: float
    bounce_count: int
    transactions: list[dict]
    issue: list[str]
    missing: list[dict]
    ask: dict
    receipt: dict
    reply: str
    title: str
    query_result: Any
    next_after_ask: str
    evidence: list[dict]
    pending_index: int
    pending_field: str
    pending_write: dict
    match_accounts: list[str]
    match_message: str


class AgentGraph:
    def __init__(self, settings: Settings, database: Database, ledgers: LedgerFactory, model: AgentModel,
                 vectors: VectorIndexManager | None = None):
        self.settings = settings
        self.database = database
        self.ledgers = ledgers
        self.model = model
        self.vectors = vectors

    async def classify(self, state: AgentState) -> dict:
        result = await self.model.classify(state['message'], state.get('history', []))
        return {'intent': result.intent, 'confidence': result.confidence}

    def route_intent(self, state: AgentState) -> str:
        return route_classification(
            Classification(intent=state['intent'], confidence=state['confidence']),
            self.settings.intent_threshold,
        )

    async def extract(self, state: AgentState) -> dict:
        ledger = self.ledgers.get(state['user'])
        examples = await self.vectors.search(state['user'], state['message']) if self.vectors else []
        batch = await self.model.extract(
            state['message'], [(a, n) for a, n in ledger.postable_accounts_with_names() if not a.startswith('Equity:')], examples, date.today()
        )
        transactions = [item.model_dump(mode='json') for item in batch.transactions]
        issues = extraction_issues(state['message'], batch.transactions)
        if not transactions:
            issues.append('没有识别到交易，请补充金额与交易说明')
        evidence: list[dict] = []
        parents = ledger.parent_accounts
        refused: list[str] = []
        transactions = [normalize(item) for item in transactions]
        for index, transaction in enumerate(transactions):
            transaction['autofilled'] = []
            for field in FIELDS:
                if transaction.get(field) in parents:
                    refused.append(transaction[field])
                    transaction[field] = None
                if transaction.get(field) and (transaction[field] not in ledger.accounts or transaction[field].startswith('Equity:')):
                    transaction[field] = None
                matches = account_confidence(transaction['payee'], role_history(ledger, field))
                side = '流出' if field == 'from_account' else '流入'
                evidence.extend(item.model_dump(mode='json') | {'label': f'{side}：{item.label}', 'transaction': index + 1, 'field': field} for item in matches)
                allowed = {a for a, _ in allowed_accounts(ledger, transaction, field)}
                if not issues and not transaction.get(field) and matches and matches[0].ratio >= self.settings.confidence_threshold and matches[0].account in allowed:
                    transaction[field] = matches[0].account
                    transaction['autofilled'].append(field)
        transactions = [normalize(item) for item in transactions]
        # 汇总账户只挂预算和出报表（ADR 0016），清空后让用户选具体分类。
        message = ''.join(f'{account} 是汇总账户，请选择它下面的具体分类。' for account in dict.fromkeys(refused))
        return {'transactions': transactions, 'issue': issues, 'missing': missing_fields(transactions), 'evidence': evidence, 'match_accounts': [], 'match_message': message}

    def route_extract(self, state: AgentState) -> str:
        return route_after_extract(state.get('issue', []), state.get('bounce_count', 0), state.get('missing'))

    async def bounce(self, state: AgentState) -> dict:
        return {'bounce_count': state.get('bounce_count', 0) + 1}

    async def prepare_ask(self, state: AgentState) -> dict:
        ledger = self.ledgers.get(state['user'])
        missing = state.get('missing', missing_fields(state.get('transactions', [])))
        if state.get('issue') or not missing:
            return {'ask': {'question': '请补充：' + '、'.join(state.get('issue') or ['请说明要记的交易']), 'candidates': []},
                    'pending_field': ''}
        index, field = missing[0]['index'], missing[0]['field']
        transaction = state['transactions'][index]
        options = candidates(ledger, transaction, field, self.settings.clarification_candidate_limit)
        if state.get('match_accounts'):
            options = [{'account': a, 'display_name': n or a} for a, n in allowed_accounts(ledger, transaction, field)
                       if a in state['match_accounts']]
        names = [item['display_name'] for item in options]
        # 同名账户保留路径，按钮也能唯一定位。
        labels = [item['display_name'] if names.count(item['display_name']) == 1 else item['account'] for item in options]
        side = '流出' if field == 'from_account' else '流入'
        return {'ask': {'question': state.get('match_message', '') + f'第 {index + 1} 笔请选择资金{side}账户',
                        'candidates': labels, 'default': labels[0] if labels else None},
                'pending_index': index, 'pending_field': field}

    async def ask(self, state: AgentState) -> dict:
        answer = interrupt(state['ask'])
        transactions = [dict(item) for item in state.get('transactions', [])]
        if transactions and state.get('pending_field'):
            ledger = self.ledgers.get(state['user'])
            answer_text = str(answer).strip().casefold()
            index = state.get('pending_index', 0)
            field = state['pending_field']
            options = allowed_accounts(ledger, transactions[index], field)
            matches = [
                item for item in options
                if answer_text and (answer_text in item[0].casefold() or (item[1] and answer_text in item[1].casefold()))
            ]
            exact_display = [item for item in options if item[1] and answer_text == item[1].casefold()]
            exact = [item for item in matches if answer_text == item[0].casefold()]
            matches = exact_display or exact or matches
            if len(matches) == 1:
                transactions[index][field] = matches[0][0]
                transactions[index] = normalize(transactions[index])
                missing = missing_fields(transactions)
                return {
                    'transactions': transactions, 'missing': missing, 'issue': [],
                    'match_accounts': [], 'match_message': '',
                    'next_after_ask': 'prepare_ask' if missing else 'tools',
                }
            return {'next_after_ask': 'prepare_ask', 'match_accounts': [a for a, _ in matches],
                    'match_message': '匹配到多个账户，请再选择。' if matches else '没有匹配的账户，请重新选择。'}
        return {'message': str(answer), 'next_after_ask': 'classify', 'bounce_count': 0, 'issue': [], 'transactions': [], 'missing': []}

    def route_after_ask(self, state: AgentState) -> str:
        return state.get('next_after_ask', 'classify')

    async def tools(self, state: AgentState) -> dict:
        """只渲染将要写入的内容，落盘等用户确认（ADR 0012）。"""
        ledger = self.ledgers.get(state['user'])
        transactions = [TransactionInput.model_validate(item) for item in state['transactions']]
        preview = ledger.preview(transactions)
        # 图运行期间 checkpointer 占着同一个 SQLite 文件，落库一律推迟到 stream() 收尾。
        pending_id = uuid4().hex
        count = len(transactions)
        return {
            'pending_write': {
                'id': pending_id, 'kind': 'record',
                'payload': {'transactions': state['transactions']},
            },
            'receipt': preview | {'pending_id': pending_id, 'transactions': preview_accounts(ledger, state['transactions'], self.settings.clarification_candidate_limit)},
            'reply': f'这 {count} 笔已经准备好，确认后写入账本。' if count > 1
                     else '这笔已经准备好，确认后写入账本。',
        }

    async def query(self, state: AgentState) -> dict:
        ledger = self.ledgers.get(state['user'])
        ledger.reload()
        accounts = [(a, n) for a, n in ledger.accounts_with_names() if not a.startswith('Equity:')]
        plan = await self.model.query(state['message'], accounts, date.today())
        original = plan.model_dump(mode='json')
        result: Any
        prefix = normalize_prefix(plan.arguments.account_prefix if plan.tool == 'query_transactions' and plan.arguments
                                  else plan.account_prefix)
        if plan.tool in ('query_transactions', 'get_balance', 'list_accounts') and prefix and not any(
            account_matches(account, prefix) for account in ledger.accounts
        ):
            matches = [a for a, n in accounts if n and n in state['message']]
            matches.extend(get_close_matches(prefix, [a for a, _ in accounts], n=3, cutoff=0.6))
            matches = list(dict.fromkeys(matches))[:3]
            names = dict(accounts)
            suggestions = [{'account': a, 'display_name': names[a] or a} for a in matches]
            if matches:
                labels = '、'.join(f'{names[a]}（{a}）' if names[a] else a for a in matches)
                reply = f'账本里没有 `{prefix}` 这个账户。你是不是想查：{labels}？'
            else:
                reply = f'账本里没有 `{prefix}` 这个账户，可以问我『我有哪些账户』。'
            result = {'error': 'account_not_found', 'account_prefix': prefix, 'candidates': suggestions}
            return {'query_result': result, 'reply': reply,
                    'receipt': {'tool': plan.tool, 'arguments': original, 'result': result}}

        if plan.tool == 'list_accounts':
            result = [{'account': account, 'display_name': name} for account, name in ledger.accounts_with_names()
                      if account_matches(account, prefix)]
        elif plan.tool == 'get_balance':
            result = ledger.balances(prefix, plan.as_of or date.today())
        elif plan.tool == 'budget_status':
            result = ledger.budget_status()
        elif plan.arguments:
            result = ledger.query_transactions(
                plan.arguments.start, plan.arguments.end, prefix,
                plan.arguments.payee, plan.arguments.limit,
                Decimal(str(plan.arguments.min_amount)) if plan.arguments.min_amount is not None else None,
                Decimal(str(plan.arguments.max_amount)) if plan.arguments.max_amount is not None else None,
                plan.arguments.group_by, plan.arguments.order_by,
            )
        else:
            result = {'error': '查询参数不足'}
        return {
            'query_result': result, 'reply': self._query_reply(result, plan, dict(accounts)),
            'receipt': {'tool': plan.tool, 'arguments': original, 'result': result},
        }

    @staticmethod
    def _budget_reply(rows: list[dict]) -> str:
        if not rows:
            return '还没有设置任何预算。'
        return '；'.join(
            f"{row['display_name']}：已用 {row['used']} / 上限 {row['amount']}，剩余 {row['remaining']}"
            for row in rows
        ) + '。'

    @staticmethod
    def _query_reply(result: Any, plan: Any = None, names: dict | None = None) -> str:
        if plan is not None and getattr(plan, 'tool', None) == 'budget_status':
            return AgentGraph._budget_reply(result)
        if isinstance(result, dict) and result.get('error'):
            return result['error']
        if plan and plan.tool == 'list_accounts':
            return f'共 {len(result)} 个账户。'
        if isinstance(result, list) and plan and plan.arguments:
            args = plan.arguments
            prefix = normalize_prefix(args.account_prefix)
            name = (names or {}).get(prefix)
            label = f'{name}（{prefix}）' if name else (f'{prefix} ' if prefix else '')
            scope = f'{args.start.isoformat()} 至 {args.end.isoformat()}，{label}'
            if not result:
                return scope + '没有记录。'
            if args.group_by != 'none':
                total = sum((Decimal(row['amount']) for row in result), Decimal())
                return f'{scope}共 {len(result)} 组，金额合计 {total:.2f}。'
            if args.order_by == 'amount_desc':
                top = result[0]
                head = '金额最大的一笔是' if len(result) == 1 else f'金额最大的 {len(result)} 笔里，第一笔是'
                return f"{scope}{head} {top['date']} {top['payee'] or ''} · {top['narration']}，{top['amount']}。"
            total = sum((Decimal(posting['amount']) for row in result for posting in row.get('postings', [])
                         if posting.get('amount') and account_matches(posting.get('account', ''), 'Expenses')), Decimal())
            return f'{scope}共 {len(result)} 笔，支出合计 {total:.2f}。'
        return f'查询结果：{result}'

    async def budget(self, state: AgentState) -> dict:
        ledger = self.ledgers.get(state['user'])
        plan = await self.model.budget(state['message'], ledger.accounts_with_names())
        if not plan.account or not plan.amount:
            ask = {'question': '请补充预算账户和金额', 'candidates': [name or account for account, name in ledger.accounts_with_names()]}
            return {'ask': ask, 'issue': ['预算账户或金额不明确'], 'next_after_ask': 'classify'}
        preview = ledger.preview_budget(plan.account, plan.amount, plan.period)
        pending_id = uuid4().hex
        return {
            'pending_write': {
                'id': pending_id, 'kind': 'budget',
                'payload': {'account': plan.account, 'amount': str(plan.amount), 'period': plan.period},
            },
            'receipt': preview | {'pending_id': pending_id},
            'reply': f'确认后把 {plan.account} 的{plan.period}预算设为 {plan.amount}。',
        }

    async def other(self, state: AgentState) -> dict:
        return {'issue': ['请把记账、查询或预算请求分开发送']}

    def run_title(self, state: AgentState) -> str:
        """给这次运行起个能在历史列表里认出来的名字。"""
        intent = state.get('intent')
        if intent == 'record':
            transactions = state.get('transactions', [])
            payee = next((item.get('payee') for item in transactions if item.get('payee')), '')
            directions = {flow_direction(item.get('from_account'), item.get('to_account')) for item in transactions}
            direction = directions.pop() if len(directions) == 1 else None
            return f'记录{payee}{direction or "交易"}' if payee else '记录一笔交易'
        if intent == 'query':
            return '查询账本'
        if intent == 'budget':
            account = (state.get('receipt') or {}).get('account', '')
            names = dict(self.ledgers.get(state['user']).accounts_with_names()) if account else {}
            return f'设置{names.get(account) or account}预算' if account else '设置预算'
        return '处理消息'

    async def reply(self, state: AgentState) -> dict:
        return {'message': state.get('reply', '已完成'), 'title': self.run_title(state)}

    def builder(self) -> StateGraph:
        graph = StateGraph(AgentState)
        for name in ('classify', 'extract', 'bounce', 'prepare_ask', 'ask', 'tools', 'query', 'budget', 'other', 'reply'):
            graph.add_node(name, getattr(self, name))
        graph.add_edge(START, 'classify')
        graph.add_conditional_edges('classify', self.route_intent, {
            'record': 'extract', 'query': 'query', 'budget': 'budget', 'ask': 'other',
        })
        graph.add_conditional_edges('extract', self.route_extract, {
            'tools': 'tools', 'classify': 'bounce', 'ask': 'prepare_ask',
        })
        graph.add_edge('bounce', 'classify')
        graph.add_edge('other', 'prepare_ask')
        graph.add_edge('prepare_ask', 'ask')
        graph.add_conditional_edges('ask', self.route_after_ask, {
            'classify': 'classify', 'tools': 'tools', 'prepare_ask': 'prepare_ask',
        })
        graph.add_edge('tools', 'reply')
        graph.add_edge('query', 'reply')
        graph.add_conditional_edges('budget', lambda state: 'ask' if state.get('ask') else 'reply',
                                    {'ask': 'ask', 'reply': 'reply'})
        graph.add_edge('reply', END)
        return graph

    async def stream(self, input_state: AgentState | Command, graph_thread_id: str) -> AsyncIterator[dict]:
        config: RunnableConfig = {'configurable': {'thread_id': graph_thread_id}}
        run_id = input_state['run_id'] if isinstance(input_state, dict) else graph_thread_id.rsplit(':', 1)[-1]
        pending_steps: list[tuple[str, str, dict, int]] = []
        pending_writes: list[dict] = []
        pending_intent: str | None = None
        pending_title: str | None = None
        terminal_ask: dict | None = None
        async with AsyncSqliteSaver.from_conn_string(str(self.settings.database_path)) as saver:
            graph = self.builder().compile(checkpointer=saver)
            node_started = perf_counter()
            async for update in graph.astream(input_state, config, stream_mode='updates'):
                duration_ms = int((perf_counter() - node_started) * 1000)
                node_started = perf_counter()
                if '__interrupt__' in update:
                    interrupts = update['__interrupt__']
                    terminal_ask = {'type': 'ask', **interrupts[0].value}
                    break
                for node, payload in update.items():
                    step_info = {
                        'classify': ('CLASSIFY', '识别意图'),
                        'extract': ('PARSE', '抽取交易'),
                        'prepare_ask': ('ASK', '向用户追问'),
                        'tools': ('TOOL', '写入账本'),
                        'query': ('TOOL', '查询账本'),
                        'budget': (('ASK', '追问预算') if payload.get('ask') else ('TOOL', '设置预算')),
                        'reply': ('REPLY', '生成回复'),
                    }.get(node)
                    if step_info:
                        pending_steps.append((step_info[0], step_info[1], payload, duration_ms))
                    if payload.get('pending_write'):
                        pending_writes.append(payload['pending_write'])
                    if node == 'classify':
                        pending_intent = payload['intent']
                    if node == 'reply':
                        pending_title = payload['title']
                    # 时间线是三层呈现的第一层，每个节点都要出现在上面；结果卡是第三层，
                    # 两者描述的是同一次调用，所以先发 step 再发 message / receipt。
                    if node != 'ask':
                        yield {
                            'type': 'step', 'node': node,
                            'kicker': step_info[0] if step_info else None,
                            'title': step_info[1] if step_info else node,
                            'duration_ms': duration_ms, 'payload': payload,
                        }
                    if node == 'reply':
                        yield {'type': 'message', 'content': payload['message']}
                    elif payload.get('receipt'):
                        yield {'type': 'receipt', **payload['receipt']}
        user_id = input_state['user']['id'] if isinstance(input_state, dict) else None
        for write in pending_writes:
            self.database.create_pending(
                user_id or self.database.rows('SELECT user_id FROM runs WHERE id=?', (run_id,))[0]['user_id'],
                run_id, write['kind'], write['payload'], write['id'],
            )
        for kicker, title, payload, duration_ms in pending_steps:
            self.database.add_step(run_id, kicker, title, payload, duration_ms)
        if pending_intent:
            self.database.execute('UPDATE runs SET intent=? WHERE id=?', (pending_intent, run_id))
        if pending_title:
            # 追问发生在上一轮，所以从落库的步骤里判断，而不是本轮的 pending_steps。
            asked = any(step['kicker'] == 'ASK' for step in self.database.steps(run_id))
            self.database.execute(
                'UPDATE runs SET title=? WHERE id=?',
                (pending_title + ('（含追问）' if asked else ''), run_id),
            )
        if terminal_ask:
            yield terminal_ask
            return
        yield {'type': 'done'}
