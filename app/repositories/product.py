from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.product import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    model = Product

    async def get_by_sku(self, sku: str) -> Product | None:
        return await self.get_by(sku=sku)

    async def get_for_update(self, product_id: uuid.UUID) -> Product | None:
        """Carrega o produto com lock pessimista (``SELECT ... FOR UPDATE``).

        Garante serialização de movimentações concorrentes sobre o mesmo produto,
        evitando saldo incorreto em condições de corrida.
        """
        stmt = select(Product).where(Product.id == product_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
