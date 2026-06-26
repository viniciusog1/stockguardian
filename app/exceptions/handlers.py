"""Tradução de exceções de domínio → respostas HTTP padronizadas.

Centraliza o mapeamento para que serviços nunca levantem ``HTTPException``. Todas
as respostas de erro seguem o mesmo envelope JSON.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.exceptions.domain import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainError,
    InsufficientStockError,
    NotFoundError,
    ValidationError,
)

logger = get_logger(__name__)

# Mapeia cada exceção de domínio para o status HTTP adequado.
_STATUS_MAP: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    ValidationError: 422,  # Unprocessable Content
    InsufficientStockError: status.HTTP_409_CONFLICT,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    AuthorizationError: status.HTTP_403_FORBIDDEN,
}


def _error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        http_status = _STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
        if http_status >= 500:
            logger.error("domain_error", code=exc.code, message=exc.message)
        else:
            logger.info("domain_error", code=exc.code, message=exc.message)
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthenticationError) else None
        return JSONResponse(
            status_code=http_status,
            content=_error_body(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,  # Unprocessable Content
            content=_error_body(
                "request_validation_error",
                "Erro de validação na requisição.",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", "Erro interno do servidor."),
        )
