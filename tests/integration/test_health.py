"""Integração: probes de liveness e readiness."""

from __future__ import annotations

import pytest
from app.dependencies.db import get_redis_client
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_readiness_ok(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


async def test_readiness_503_when_redis_down(client: AsyncClient) -> None:
    class _FailRedis:
        async def ping(self) -> bool:
            raise RuntimeError("redis down")

    app = client._app  # type: ignore[attr-defined]
    app.dependency_overrides[get_redis_client] = lambda: _FailRedis()
    try:
        resp = await client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_redis_client, None)
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"]["redis"]["status"] == "error"
    assert body["checks"]["database"]["status"] == "ok"
