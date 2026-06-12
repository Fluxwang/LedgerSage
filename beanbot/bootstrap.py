from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
# from typing import Any

from beanbot.bots.controller import BotController
from beanbot.gateways.beancount_repo import BeancountRepository
from beanbot.i18n import init_locale
from beanbot.logging_config import init_logging
from beanbot.services.rag_client import RagClient
from beanbot.services.vector_service import VectorService
from beanbot.services.ledger_service import LedgerService
from beanbot.services.query_service import QueryService
from beanbot.settings import Settings, load_settings
from beanbot.gateways.vector_store import create_vector_store
from beanbot.gateways.embedding_client import EmbeddingClient


@dataclass
class AppContext:
    settings: Settings
    logger: Logger
    repository: BeancountRepository
    ledger_service: LedgerService
    query_service: QueryService
    vector_service: VectorService
    controller: BotController


_context: AppContext | None = None


def get_context() -> AppContext:
    """检查是否有_context"""
    if _context is None:
        raise RuntimeError("AppContext not initialized")
    return _context


def bootstrap_app(config_path: str) -> AppContext:
    global _context

    settings = load_settings(config_path)
    init_locale(settings)
    logger = init_logging(settings)

    # 初始化 repository
    repository = BeancountRepository(
        filename=str(settings.beancount.filename),
        currency=str(settings.beancount.currency),
        logger=logger,
    )
    if settings.embedding.get("enable", False):
        embedding_client = EmbeddingClient(settings)
        vector_store = create_vector_store(settings)
        rag_client = RagClient(settings)
    else:
        embedding_client = None
        vector_store = None
        rag_client = None

    vector_service = VectorService(
        settings=settings,
        embedding_client=embedding_client,
        vector_store=vector_store,
        rag_client=rag_client,
        logger=logger,
    )

    # 初始化 ledger_service
    ledger_service = LedgerService(
        settings=settings, repository=repository, vector_service=vector_service
    )

    # 初始化query_service
    query_service = QueryService(repository=repository)

    controller = BotController(
        settings=settings,
        repository=repository,
        ledger_service=ledger_service,
        query_service=query_service,
        vector_service=vector_service,
    )
    from beanbot.bots.controller import configure as configure_controller

    configure_controller(controller)

    context = AppContext(
        settings=settings,
        logger=logger,
        repository=repository,
        ledger_service=ledger_service,
        query_service=query_service,
        vector_service=vector_service,
        controller=controller,
    )

    global _context
    _context = context
    return context
