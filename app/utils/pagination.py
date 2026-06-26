"""Helper de paginação para uso como dependência nas rotas."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from app.schemas.common import PaginationParams


def pagination_params(
    page: Annotated[int, Query(ge=1, description="Página (1-based).")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Itens por página.")] = 20,
) -> PaginationParams:
    return PaginationParams(page=page, size=size)


Pagination = Annotated[PaginationParams, Depends(pagination_params)]
