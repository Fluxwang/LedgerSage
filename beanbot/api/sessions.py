"""按运行回放用户自己的历史对话，不读取 LangGraph checkpoint。"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Request

from beanbot.api.auth import CurrentUser
from beanbot.exceptions import NotFound
from beanbot.gateways.ledger import TransactionInput
from beanbot.services.agent.accounts import preview_accounts
from beanbot.services.pending_service import PENDING_TTL

router = APIRouter(prefix='/sessions')


def ask_state(session: dict) -> dict:
    pending_at = session.get('pending_at')
    active = bool(session.get('active_run_id') and pending_at)
    expired = bool(active and pending_at and datetime.now(timezone.utc) - datetime.fromisoformat(pending_at) > timedelta(hours=24))
    return {'has_pending_ask': active and not expired, 'ask_expired': expired}


@router.get('')
async def list_sessions(request: Request, user: CurrentUser):
    rows = request.app.state.db.rows(
        'SELECT * FROM sessions WHERE user_id=? ORDER BY last_active_at DESC,id DESC LIMIT 30',
        (user['id'],),
    )
    return [{key: row[key] for key in ('thread_id', 'title', 'last_active_at')} |
            {'has_pending_ask': ask_state(row)['has_pending_ask']} for row in rows]


@router.get('/{thread_id}/runs')
async def replay_session(thread_id: str, request: Request, user: CurrentUser):
    database = request.app.state.db
    rows = database.rows('SELECT * FROM sessions WHERE user_id=? AND thread_id=?', (user['id'], thread_id))
    if not rows:
        raise NotFound('对话不存在')
    session = rows[0]
    runs = database.rows('SELECT * FROM runs WHERE session_id=? AND user_id=? ORDER BY created_at,id',
                         (session['id'], user['id']))
    for run in runs:
        run['steps'] = database.steps(run['id'])
        records = database.rows('SELECT * FROM pending_writes WHERE run_id=? AND user_id=? ORDER BY created_at,id',
                                (run['id'], user['id']))
        for record in records:
            record['payload'] = json.loads(record['payload'])
            if record['status'] == 'pending' and datetime.now(timezone.utc) - datetime.fromisoformat(record['created_at']) > PENDING_TTL:
                record['status'] = 'expired'
            # 回放采用最新编辑过的 payload；终态保留当时的步骤回执，不重新校验旧账务。
            if record['status'] == 'pending':
                ledger = request.app.state.ledgers.get(user)
                payload = record['payload']
                if record['kind'] == 'record':
                    receipt = ledger.preview([TransactionInput.model_validate(item) for item in payload['transactions']])
                    receipt['transactions'] = preview_accounts(ledger, payload['transactions'], request.app.state.settings.clarification_candidate_limit)
                else:
                    receipt = ledger.preview_budget(payload['account'], Decimal(str(payload['amount'])))
                record['receipt'] = receipt | {'pending_id': record['id']}
        run['pending_writes'] = records
    return {**session, **ask_state(session), 'runs': runs}
