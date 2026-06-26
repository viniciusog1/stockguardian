"""Helper de cache-aside sobre Redis.

Padrão get-or-set: tenta o cache; no miss, computa via `factory`, grava como
JSON com TTL e retorna. Reutilizável por qualquer endpoint cacheável.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

from redis.asyncio import Redis

T = TypeVar("T")


async def get_or_set(
    redis: Redis,
    key: str,
    ttl: int,
    factory: Callable[[], Awaitable[T]],
) -> T:
    cached = await redis.get(key)
    if cached is not None:
        return cast(T, json.loads(cached))
    value = await factory()
    await redis.set(key, json.dumps(value), ex=ttl)
    return value
