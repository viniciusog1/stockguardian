from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Row, select

from app.models.product import Product
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    model = Product

    async def get_by_sku(self, sku: str) -> Product | None:
        return await self.get_by(sku=sku)

    async def inventory_valuation(
        self, *, supplier_id: uuid.UUID | None = None, only_active: bool = True
    ) -> Sequence[Row[tuple[uuid.UUID, str, str, int, Decimal, Decimal]]]:
        """Linhas de valuation: produto + valor parado em estoque (quantity * preço)."""
        # unit_price (Decimal) à esquerda garante que a expressão seja tipada/retornada
        # como Decimal (Numeric), não int.
        stock_value = (Product.unit_price * Product.quantity).label("stock_value")
        stmt = select(
            Product.id,
            Product.sku,
            Product.name,
            Product.quantity,
            Product.unit_price,
            stock_value,
        )
        if only_active:
            stmt = stmt.where(Product.is_active.is_(True))
        if supplier_id is not None:
            stmt = stmt.where(Product.supplier_id == supplier_id)
        stmt = stmt.order_by(stock_value.desc(), Product.sku.asc())
        result = await self.session.execute(stmt)
        return result.all()

    async def get_for_update(self, product_id: uuid.UUID) -> Product | None:
        """Carrega o produto com lock pessimista (``SELECT ... FOR UPDATE``).

        Garante serialização de movimentações concorrentes sobre o mesmo produto,
        evitando saldo incorreto em condições de corrida.
        """
        stmt = select(Product).where(Product.id == product_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
