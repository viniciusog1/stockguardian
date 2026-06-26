"""Configuração do worker ARQ.

Executar: ``arq app.worker.settings.WorkerSettings``.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.core.queue import report_redis_settings
from app.worker.tasks import (
    generate_inventory_valuation_export,
    generate_movements_summary_export,
)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["session_factory"] = async_session_factory


async def shutdown(ctx: dict[str, Any]) -> None:
    await engine.dispose()


class WorkerSettings:
    functions = [generate_inventory_valuation_export, generate_movements_summary_export]
    redis_settings = report_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    keep_result = settings.REPORT_JOB_RESULT_TTL
