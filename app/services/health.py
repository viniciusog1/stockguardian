"""Serviço de health/readiness: checa dependências (DB, Redis)."""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.health import CheckResult, ReadinessResponse


class HealthService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis

    async def _check_db(self) -> CheckResult:
        try:
            await self.session.execute(text("SELECT 1"))
            return CheckResult(status="ok")
        except Exception as exc:
            # readiness reporta a falha; não propaga (não derruba a request)
            return CheckResult(status="error", detail=str(exc))

    async def _check_redis(self) -> CheckResult:
        try:
            await self.redis.ping()
            return CheckResult(status="ok")
        except Exception as exc:
            return CheckResult(status="error", detail=str(exc))

    async def readiness(self) -> ReadinessResponse:
        checks = {
            "database": await self._check_db(),
            "redis": await self._check_redis(),
        }
        ready = all(c.status == "ok" for c in checks.values())
        return ReadinessResponse(ready=ready, checks=checks)
