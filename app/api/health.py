"""Probes de liveness e readiness (raiz, sem autenticação)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.dependencies.db import DBSession, RedisClient
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=LivenessResponse, summary="Liveness probe")
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok", service=settings.PROJECT_NAME)


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(
    session: DBSession, redis: RedisClient, response: Response
) -> ReadinessResponse:
    result = await HealthService(session, redis).readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
