"""运行历史分页、筛选与详情。"""

from fastapi import APIRouter, Depends, Query, Request

from beanbot.api.auth import get_current_user
from beanbot.exceptions import NotFound

router = APIRouter(prefix="/runs")


@router.get("")
async def list_runs(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    intent: str | None = None,
    asked: bool = False,
    user: dict = Depends(get_current_user),
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
    run_id: str, request: Request, user: dict = Depends(get_current_user)
):
    database = request.app.state.db
    run = database.run(run_id, user["id"])
    if not run:
        raise NotFound("运行不存在")
    return {**run, "steps": database.steps(run_id)}
