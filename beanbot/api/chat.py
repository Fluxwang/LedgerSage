"""对话 SSE 接口。"""

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from beanbot.api.auth import CurrentUser

router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str = Field(min_length=1, max_length=128)


class PendingEdit(BaseModel):
    transaction_index: int = Field(ge=0)
    from_account: str | None = Field(default=None, min_length=1)
    to_account: str | None = Field(default=None, min_length=1)


@router.patch('/pending/{pending_id}')
async def edit_pending(pending_id: str, body: PendingEdit, request: Request,
                       user: CurrentUser):
    return request.app.state.pending.edit(user, pending_id, body.transaction_index,
                                         body.model_dump(exclude={'transaction_index'}, exclude_none=True))


def sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: CurrentUser,
):
    async def events():
        try:
            async for event in request.app.state.chat.stream(
                user, body.thread_id, body.message
            ):
                yield sse(event)
        except Exception as exc:
            yield sse({"type": "error", "detail": str(exc)})

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.post("/pending/{pending_id}/confirm")
async def confirm_pending(
    pending_id: str,
    request: Request,
    user: CurrentUser,
):
    """把 Agent 产出的 diff 真正写进账本（ADR 0012）。"""
    return await request.app.state.pending.confirm(user, pending_id)


@router.post("/pending/{pending_id}/reject")
async def reject_pending(
    pending_id: str,
    request: Request,
    user: CurrentUser,
):
    return request.app.state.pending.reject(user, pending_id)