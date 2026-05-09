from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from beanbot.bots.controller import BotController
from beanbot.gateways.beancount_repo import BeancountRepository
from beanbot.i18n import init_locale
from beanbot.logging_config import init_logging
from beanbot.services.ledger_service import LedgerService
from beanbot.services.query_service import QueryService
from beanbot.settings import Settings, load_settings


@dataclass
class AppContext:
    settings: Settings
    logger: Any
    repository: BeancountRepository
    ledger_service: LedgerService
    query_service: QueryService
    controller: BotController


_context = None


def get_context():
    """检查是否有_context"""
    if _context is None:
        raise RuntimeError("AppContext not initialized")
    return _context


def bootstrap_app(config_path: str) -> AppContext:
    settings = load_settings(config_path)
    init_locale(settings)
    logger = init_logging(settings)

    # 初始化 repository
    repository = BeancountRepository(
        filename=str(settings.beancount.filename),
        currency=str(settings.beancount.currency),
        logger=logger,
    )

    # 初始化 ledger_service
    ledger_service = LedgerService(
        settings=settings,
        repository=repository,
        vector_service=None,
    )

    # 初始化query_service
    query_service = QueryService(repository=repository)

    controller = BotController(
        settings=settings,
        repository=repository,
        ledger_service=ledger_service,
        query_service=query_service,
        vector_service=None,
    )

    from beanbot.bots.controller import configure as configure_controller

    configure_controller(controller)

    context = AppContext(
        settings=settings,
        logger=logger,
        repository=repository,
        ledger_service=ledger_service,
        query_service=query_service,
        controller=controller,
    )

    global _context
    _context = context
    return context
