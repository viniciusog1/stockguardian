"""Serviço do dashboard operacional.

Calcula contadores gerais e serve com cache-aside no Redis.
"""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_or_set
from app.core.config import settings
from app.repositories.product import ProductRepository
from app.repositories.supplier import SupplierRepository
from app.repositories.user import UserRepository

_SUMMARY_CACHE_KEY = "dashboard:summary"


class DashboardService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis

    async def summary(self) -> dict[str, int]:
        async def factory() -> dict[str, int]:
            return {
                "active_products": await ProductRepository(self.session).count(is_active=True),
                "active_suppliers": await SupplierRepository(self.session).count(is_active=True),
                "total_users": await UserRepository(self.session).count(),
            }

        return await get_or_set(
            self.redis, _SUMMARY_CACHE_KEY, settings.DASHBOARD_CACHE_TTL, factory
        )
