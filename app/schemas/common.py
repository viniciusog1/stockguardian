"""Schemas genéricos: paginação e envelope de erro."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Parâmetros de paginação por offset (query params)."""

    page: int = Field(default=1, ge=1, description="Página (1-based).")
    size: int = Field(default=20, ge=1, le=100, description="Itens por página.")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


class Page(BaseModel, Generic[T]):
    """Resposta paginada padronizada."""

    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: list[T], total: int, params: PaginationParams) -> Page[T]:
        pages = (total + params.size - 1) // params.size if total else 0
        return cls(items=items, total=total, page=params.page, size=params.size, pages=pages)
