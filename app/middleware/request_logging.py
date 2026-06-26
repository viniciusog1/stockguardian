"""Middleware de logging por request com correlation-id.

Injeta um ``correlation_id`` (do header ``X-Request-ID`` ou gerado) no contexto
do structlog, propagando-o para todos os logs daquele request e devolvendo-o no
header da resposta — facilita rastrear uma requisição ponta a ponta.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger("http")

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = request.headers.get(_REQUEST_ID_HEADER, str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed")
            structlog.contextvars.clear_contextvars()
            raise

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request_completed",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        response.headers[_REQUEST_ID_HEADER] = correlation_id
        structlog.contextvars.clear_contextvars()
        return response
