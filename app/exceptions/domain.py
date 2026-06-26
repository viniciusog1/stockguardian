"""Exceções de domínio.

A camada de serviço/repositório levanta estas exceções — independentes de HTTP.
A tradução para respostas HTTP acontece em `app.exceptions.handlers`, mantendo o
domínio desacoplado do framework web.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base para todos os erros de negócio.

    Attributes:
        message: mensagem legível ao cliente.
        code: identificador estável da máquina (ex.: ``not_found``).
        details: dados estruturados adicionais (ex.: campo em conflito).
    """

    code: str = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    code = "not_found"

    def __init__(self, resource: str, identifier: Any = None) -> None:
        msg = f"{resource} não encontrado(a)."
        details = {"resource": resource}
        if identifier is not None:
            details["identifier"] = str(identifier)
        super().__init__(msg, details=details)


class ConflictError(DomainError):
    """Violação de unicidade ou estado conflitante (ex.: SKU duplicado)."""

    code = "conflict"


class ValidationError(DomainError):
    """Regra de negócio violada (distinto da validação de schema do Pydantic)."""

    code = "validation_error"


class AuthenticationError(DomainError):
    """Credenciais inválidas ou token ausente/expirado."""

    code = "authentication_error"


class AuthorizationError(DomainError):
    """Usuário autenticado, mas sem permissão para a ação."""

    code = "authorization_error"


class InsufficientStockError(DomainError):
    """Saída/ajuste deixaria o estoque negativo."""

    code = "insufficient_stock"

    def __init__(self, *, available: int, requested: int, product_id: Any = None) -> None:
        super().__init__(
            f"Estoque insuficiente: disponível {available}, solicitado {requested}.",
            details={
                "available": available,
                "requested": requested,
                "product_id": str(product_id) if product_id is not None else None,
            },
        )
