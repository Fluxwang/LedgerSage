"""按运行回放用户自己的历史对话，不读取 LangGraph checkpoint。"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from beanbot.api.auth import CurrentUser
from beanbot.exceptions import DomainError, NotFound
from beanbot.gateways.ledger import Ledger, TransactionInput
from beanbot.services.agent.accounts import preview_accounts
from beanbot.services.pending_service import PENDING_TTL

router = APIRouter(prefix='/sessions')


class RenameSession(BaseModel):
    title: str


@router.patch('/{thread_id}')
def rename_session(thread_id: str, body: RenameSession, request: Request, user: CurrentUser):
    title = body.title.strip()
    maximum = request.app.state.settings.conversation_title_max_length
    if not 1 <= len(title) <= maximum:
        raise HTTPException(status_code=422, detail=f'对话标题不能为空，且不能超过 {maximum} 个字')
    if not request.app.state.db.rename_session(user['id'], thread_id, title):
        raise NotFound('对话不存在')
    return {'thread_id': thread_id, 'title': title}


@router.delete('/{thread_id}', status_code=204)
def delete_session(thread_id: str, request: Request, user: CurrentUser):
    if not request.app.state.db.delete_session(user['id'], thread_id):
        raise NotFound('对话不存在')
    return Response(status_code=204)


def ask_state(session: dict) -> dict:
    pending_at = session.get('pending_at')
    active = bool(session.get('active_run_id') and pending_at)
    expired = bool(active and pending_at and datetime.now(timezone.utc) - datetime.fromisoformat(pending_at) > timedelta(hours=24))
    return {'has_pending_ask': active and not expired, 'ask_expired': expired}


@router.get('')
async def list_sessions(request: Request, user: CurrentUser):
    cutoff = (datetime.now(timezone.utc) - PENDING_TTL).isoformat()
    rows = request.app.state.db.rows(
        "SELECT s.*, (SELECT COUNT(*) FROM pending_writes p JOIN runs r ON r.id=p.run_id "
        "WHERE r.session_id=s.id AND p.user_id=s.user_id AND p.status='pending' "
        "AND julianday(p.created_at)>=julianday(?)) AS pending_write_count "
        "FROM sessions s WHERE s.user_id=? AND s.deleted_at IS NULL "
        "ORDER BY s.last_active_at DESC,s.id DESC LIMIT 30",
        (cutoff, user['id']),
    )
    return [{key: row[key] for key in ('thread_id', 'title', 'last_active_at')} |
            {'has_pending_ask': ask_state(row)['has_pending_ask'],
             'pending_write_count': row['pending_write_count']} for row in rows]


@router.get('/{thread_id}/runs')
async def replay_session(thread_id: str, request: Request, user: CurrentUser):
    database = request.app.state.db
    rows = database.rows('SELECT * FROM sessions WHERE user_id=? AND thread_id=? AND deleted_at IS NULL', (user['id'], thread_id))
    if not rows:
        raise NotFound('对话不存在')
    session = rows[0]
    runs = database.rows('SELECT * FROM runs WHERE session_id=? AND user_id=? ORDER BY created_at,id',
                         (session['id'], user['id']))
    ledger: Ledger | None = None
    load_error: DomainError | None = None
    for run in runs:
        run['steps'] = database.steps(run['id'])
        records = database.rows('SELECT * FROM pending_writes WHERE run_id=? AND user_id=? ORDER BY created_at,id',
                                (run['id'], user['id']))
        for record in records:
            record['payload'] = json.loads(record['payload'])
            if record['status'] == 'pending' and datetime.now(timezone.utc) - datetime.fromisoformat(record['created_at']) > PENDING_TTL:
                record['status'] = 'expired'
            # 回放采用最新编辑过的 payload；终态保留当时的步骤回执，不重新校验旧账务。
            if record['status'] != 'pending':
                continue
            # 账本被手改坏、账户被删时只降级这一条，会话其余部分照常回放；确认时后端仍会重新校验。
            try:
                if ledger is None and load_error is None:
                    ledger = request.app.state.ledgers.get(user)
            except DomainError as exc:
                load_error = exc
            if load_error is not None:
                record['preview_error'] = f'账本无法加载，暂时不能预览：{load_error}'
                continue
            assert ledger is not None
            payload = record['payload']
            try:
                if record['kind'] == 'record':
                    receipt = ledger.preview([TransactionInput.model_validate(item) for item in payload['transactions']])
                    receipt['transactions'] = preview_accounts(ledger, payload['transactions'], request.app.state.settings.clarification_candidate_limit)
                else:
                    receipt = ledger.preview_budget(payload['account'], Decimal(str(payload['amount'])))
            except DomainError as exc:
                record['preview_error'] = f'无法预览：{exc}'
                continue
            record['receipt'] = receipt | {'pending_id': record['id']}
        run['pending_writes'] = records
    return {**session, **ask_state(session), 'runs': runs}
