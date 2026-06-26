"""Rotas de movimentação de estoque e histórico."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.permissions import Permission
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.db import DBSession
from app.models.stock_movement import MovementType
from app.schemas.common import Page
from app.schemas.movement import MovementCreate, MovementFilter, MovementRead
from app.services.movement import MovementService
from app.utils.pagination import Pagination

router = APIRouter(prefix="/movements", tags=["movements"])

# Movimentar estoque exige movement:create (operação do dia a dia).
CanCreate = Depends(require_permission(Permission.MOVEMENT_CREATE))


@router.post(
    "", response_model=MovementRead, status_code=status.HTTP_201_CREATED, dependencies=[CanCreate]
)
async def create_movement(
    data: MovementCreate, session: DBSession, current_user: CurrentUser
) -> MovementRead:
    movement = await MovementService(session).create(data, user_id=current_user.id)
    return MovementRead.model_validate(movement)


@router.get("", response_model=Page[MovementRead])
async def list_movements(
    session: DBSession,
    _: CurrentUser,
    pagination: Pagination,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    type: Annotated[MovementType | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> Page[MovementRead]:
    filters = MovementFilter(product_id=product_id, type=type, date_from=date_from, date_to=date_to)
    page = await MovementService(session).history(filters, pagination)
    return Page[MovementRead].create(
        [MovementRead.model_validate(m) for m in page.items], page.total, pagination
    )
