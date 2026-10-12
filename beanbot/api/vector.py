"""当前用户向量索引的维护端点。"""

from fastapi import APIRouter, Request
from beanbot.api.auth import CurrentUser


router = APIRouter(prefix="/admin/vector")


@router.post("/rebuild")
async def rebuild(request: Request, user: CurrentUser):
    return request.app.state.vectors.rebuild_in_background(user)


@router.post("/rebuild/cancel")
async def cancel(request: Request, user: CurrentUser):
    return request.app.state.vectors.cancel_rebuild(user["id"])


@router.get("/status")
async def status(request: Request, user: CurrentUser):
    vectors = request.app.state.vectors
    enabled = request.app.state.settings.embedding_enabled
    result = vectors.status(user["id"])
    # 关掉 embedding 时不去连库，否则光查状态就会在账本目录里建出一个空索引。
    result["empty"] = vectors.is_empty(user) if enabled else True
    result["enabled"] = enabled
    return result
