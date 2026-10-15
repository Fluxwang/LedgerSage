"""应用组合根。"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from passlib.hash import bcrypt

from beanbot.api.auth import router as auth_router
from beanbot.api.chat import router as chat_router
from beanbot.api.ledger import router as ledger_router
from beanbot.api.runs import router as runs_router
from beanbot.api.saved_queries import router as saved_queries_router
from beanbot.api.vector import router as vector_router
from beanbot.config import Settings
from beanbot.exceptions import DomainError
from beanbot.gateways.ledger import LedgerFactory
from beanbot.services.agent.graph import AgentGraph
from beanbot.services.agent.model import AgentModel, OpenAIAgentModel
from beanbot.services.chat_service import ChatService
from beanbot.services.pending_service import PendingWriteService
from beanbot.services.vector_index import VectorIndexManager
from beanbot.storage.database import Database


def create_app(
    settings: Settings | None = None, agent_model: AgentModel | None = None
) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]  # values come from environment
    app = FastAPI(title="LedgerSage")
    app.state.settings = settings
    app.state.db = Database(settings.database_path)
    app.state.ledgers = LedgerFactory(settings)
    app.state.agent_model = agent_model or OpenAIAgentModel(settings)
    app.state.vectors = VectorIndexManager(settings, app.state.ledgers)
    app.state.agent_graph = AgentGraph(
        settings,
        app.state.db,
        app.state.ledgers,
        app.state.agent_model,
        app.state.vectors,
    )
    app.state.chat = ChatService(
        app.state.db, app.state.agent_graph, settings.llm_model
    )
    app.state.pending = PendingWriteService(
        app.state.db, app.state.ledgers, app.state.vectors
    )
    app.state.dummy_password_hash = bcrypt.using(rounds=12).hash("dummy-password")
    app.state.db.invite(settings.invite_code.get_secret_value())
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(ledger_router)
    app.include_router(runs_router)
    app.include_router(saved_queries_router)
    app.include_router(vector_router)

    # 以后不管哪里抛出 DomainError, 都由下面这个函数统一接住， 转成一个HTTP响应返回给前端
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app
