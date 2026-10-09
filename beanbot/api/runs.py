"""运行历史分页、筛选与详情。"""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from beanbot.api.auth import CurrentUser
from beanbot.exceptions import NotFound

router = APIRouter(prefix="/runs")


@router.get("")
async def list_runs(
    request: Request,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    intent: str | None = None,
    asked: bool = False,
):
    database = request.app.state.db
    return {
        "rows": database.runs(user["id"], page, size, intent, asked),
        "page": page,
        "size": size,
        "total": database.count_runs(user["id"], intent, asked),
    }


@router.get("/{run_id}")
async def run_detail(
    run_id: str, request: Request, user: CurrentUser
):
    database = request.app.state.db
    run = database.run(run_id, user["id"])
    if not run:
        raise NotFound("运行不存在")
    return {**run, "steps": database.steps(run_id)}
