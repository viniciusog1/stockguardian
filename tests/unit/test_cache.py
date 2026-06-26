"""Testes unitários do helper de cache-aside (fakeredis, sem DB)."""

from __future__ import annotations

import pytest
from app.core.cache import get_or_set
from fakeredis import aioredis as fake_aioredis

pytestmark = pytest.mark.unit


@pytest.fixture
async def redis():
    client = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


async def test_miss_calls_factory_and_caches(redis) -> None:
    calls = {"n": 0}

    async def factory() -> dict:
        calls["n"] += 1
        return {"value": 42}

    result = await get_or_set(redis, "k", 60, factory)
    assert result == {"value": 42}
    assert calls["n"] == 1
    assert await redis.get("k") is not None


async def test_hit_skips_factory(redis) -> None:
    calls = {"n": 0}

    async def factory() -> dict:
        calls["n"] += 1
        return {"value": 1}

    await get_or_set(redis, "k", 60, factory)  # miss -> popula
    result = await get_or_set(redis, "k", 60, factory)  # hit
    assert result == {"value": 1}
    assert calls["n"] == 1  # factory chamada só uma vez


async def test_sets_ttl(redis) -> None:
    async def factory() -> dict:
        return {"v": 1}

    await get_or_set(redis, "k", 30, factory)
    ttl = await redis.ttl("k")
    assert 0 < ttl <= 30
