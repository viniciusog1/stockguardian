"""Pool de conexão ARQ (Redis) — singleton, espelha app/core/redis.py.

Usado pela API para enfileirar jobs e consultar resultados. O worker usa o
mesmo Redis (ver app/worker/settings.py).
"""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

_pool: ArqRedis | None = None


def report_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )


async def get_arq_pool() -> ArqRedis:
    """Retorna um pool ARQ singleton (criado de forma lazy)."""
    global _pool
    if _pool is None:
        _pool = await create_pool(report_redis_settings())
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
