"""只收藏当前用户查询运行的原话，重放仍交给正常对话入口。"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from beanbot.api.auth import CurrentUser
from beanbot.exceptions import DomainError, NotFound

router = APIRouter(prefix="/saved-queries")


class SaveQuery(BaseModel):
    run_id: str


@router.get("")
async def list_saved_queries(request: Request, user: CurrentUser):
    return request.app.state.db.saved_queries(user["id"])


@router.post("")
async def save_query(body: SaveQuery, request: Request, user: CurrentUser):
    database = request.app.state.db
    run = database.run(body.run_id, user["id"])
    if not run:
        raise NotFound("运行不存在")
    if run["intent"] != "query":
        raise DomainError("只有查询运行可以存为常用")
    if not run.get("message"):
        raise DomainError("这次运行没有保存用户原话，无法收藏")
    return database.save_query(user["id"], run)


@router.delete("/{query_id}")
async def delete_saved_query(query_id: str, request: Request, user: CurrentUser):
    if not request.app.state.db.delete_saved_query(query_id, user["id"]):
        raise NotFound("常用查询不存在")
    return {"status": "deleted"}
