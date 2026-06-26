"""Rotas de alertas de estoque baixo."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import CurrentUser, require_role
from app.dependencies.db import DBSession
from app.models.stock_alert import AlertStatus
from app.models.user import UserRole
from app.schemas.alert import AlertFilter, AlertRead
from app.schemas.common import Page
from app.services.alert import AlertService
from app.utils.pagination import Pagination

router = APIRouter(prefix="/alerts", tags=["alerts"])

OperatorUp = Depends(require_role(UserRole.OPERATOR, UserRole.MANAGER))
ManagerUp = Depends(require_role(UserRole.MANAGER))


@router.get("", response_model=Page[AlertRead])
async def list_alerts(
    session: DBSession,
    _: CurrentUser,
    pagination: Pagination,
    status: Annotated[AlertStatus | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[AlertRead]:
    filters = AlertFilter(status=status, product_id=product_id)
    page = await AlertService(session).list(filters, pagination)
    return Page[AlertRead].create(
        [AlertRead.model_validate(a) for a in page.items], page.total, pagination
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(alert_id: uuid.UUID, session: DBSession, _: CurrentUser) -> AlertRead:
    alert = await AlertService(session).get(alert_id)
    return AlertRead.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead, dependencies=[OperatorUp])
async def acknowledge_alert(
    alert_id: uuid.UUID, session: DBSession, current_user: CurrentUser
) -> AlertRead:
    alert = await AlertService(session).acknowledge(alert_id, current_user.id)
    return AlertRead.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertRead, dependencies=[ManagerUp])
async def resolve_alert(alert_id: uuid.UUID, session: DBSession) -> AlertRead:
    alert = await AlertService(session).resolve(alert_id)
    return AlertRead.model_validate(alert)
