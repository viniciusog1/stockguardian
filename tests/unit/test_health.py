"""Unit: HealthService (checks com fakes, sem I/O real)."""

from __future__ import annotations

import pytest
from app.services.health import HealthService

pytestmark = pytest.mark.unit


class _OkSession:
    async def execute(self, *_: object) -> None:
        return None


class _FailSession:
    async def execute(self, *_: object) -> None:
        raise RuntimeError("db down")


class _OkRedis:
    async def ping(self) -> bool:
        return True


class _FailRedis:
    async def ping(self) -> bool:
        raise RuntimeError("redis down")


async def test_ready_when_all_ok() -> None:
    svc = HealthService(_OkSession(), _OkRedis())  # type: ignore[arg-type]
    result = await svc.readiness()
    assert result.ready is True
    assert result.checks["database"].status == "ok"
    assert result.checks["redis"].status == "ok"


async def test_not_ready_when_redis_down() -> None:
    svc = HealthService(_OkSession(), _FailRedis())  # type: ignore[arg-type]
    result = await svc.readiness()
    assert result.ready is False
    assert result.checks["redis"].status == "error"
    assert result.checks["database"].status == "ok"


async def test_not_ready_when_db_down() -> None:
    svc = HealthService(_FailSession(), _OkRedis())  # type: ignore[arg-type]
    result = await svc.readiness()
    assert result.ready is False
    assert result.checks["database"].status == "error"
