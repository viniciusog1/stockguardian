"""Cliente Redis async.

Usado na Fase 1 para o whitelist/revogação de refresh tokens. Nas fases
seguintes serve também de cache e broker de tarefas.
"""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import settings

_redis: Redis | None = None


def get_redis() -> Redis:
    """Retorna um cliente Redis singleton (pool de conexões interno)."""
    global _redis
    if _redis is None:
        _redis = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
