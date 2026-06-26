"""Application factory do StockGuardian.

Monta a aplicação FastAPI: configuração de logging, middleware, exception
handlers, rotas e endpoints utilitários (health). Toda a regra de negócio fica
nas camadas de serviço — aqui só há composição.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.metrics import setup_metrics
from app.core.queue import close_arq_pool
from app.core.redis import close_redis, get_redis
from app.exceptions.handlers import register_exception_handlers
from app.middleware.request_logging import RequestLoggingMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    logger.info("app_startup", environment=settings.ENVIRONMENT.value)
    # Conexão Redis é lazy; faz ping para falhar cedo se indisponível.
    try:
        await get_redis().ping()
    except Exception as exc:  # pragma: no cover - apenas log de aviso
        logger.warning("redis_unavailable", error=str(exc))
    yield
    await close_redis()
    await close_arq_pool()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="Plataforma inteligente de gestão e análise de estoque.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["health"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.PROJECT_NAME}

    if settings.METRICS_ENABLED:
        setup_metrics(app)

    return app


app = create_app()
