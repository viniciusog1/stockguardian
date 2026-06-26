"""Dependências de infraestrutura: sessão de banco e cliente Redis."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.redis import get_redis


async def get_db() -> AsyncGenerator[AsyncSession]:
    async for session in get_session():
        yield session


def get_redis_client() -> Redis:
    return get_redis()


DBSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis_client)]
