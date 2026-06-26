"""Rotas do dashboard operacional."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_role
from app.dependencies.db import DBSession, RedisClient
from app.models.user import UserRole
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(session: DBSession, redis: RedisClient) -> DashboardSummary:
    data = await DashboardService(session, redis).summary()
    return DashboardSummary.model_validate(data)
