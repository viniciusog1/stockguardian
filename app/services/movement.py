"""Serviço de movimentação de estoque — coração da regra de negócio.

Cada movimentação atualiza o saldo do produto e grava um registro histórico na
**mesma transação**. O produto é carregado com lock pessimista para serializar
movimentações concorrentes e impedir saldo negativo.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import MOVEMENTS_TOTAL
from app.exceptions.domain import InsufficientStockError, NotFoundError
from app.models.product import Product
from app.models.stock_movement import MovementType, StockMovement
from app.repositories.movement import MovementRepository
from app.repositories.product import ProductRepository
from app.schemas.common import Page, PaginationParams
from app.schemas.movement import MovementCreate, MovementFilter
from app.services.alert import AlertService

logger = get_logger(__name__)


def _apply_movement(current: int, mtype: MovementType, quantity: int) -> int:
    """Calcula o novo saldo. Levanta InsufficientStockError se ficar negativo."""
    if mtype is MovementType.IN:
        return current + quantity
    if mtype is MovementType.OUT:
        new_balance = current - quantity
        if new_balance < 0:
            raise InsufficientStockError(available=current, requested=quantity)
        return new_balance
    # ADJUSTMENT: define o valor absoluto do inventário.
    return quantity


class MovementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self.repo = MovementRepository(session)

    async def create(self, data: MovementCreate, *, user_id: uuid.UUID) -> StockMovement:
        # Lock pessimista no produto: serializa movimentações concorrentes.
        product = await self.products.get_for_update(data.product_id)
        if product is None:
            raise NotFoundError("Produto", data.product_id)

        new_balance = _apply_movement(product.quantity, data.type, data.quantity)
        product.quantity = new_balance

        movement = StockMovement(
            product_id=product.id,
            user_id=user_id,
            type=data.type,
            quantity=data.quantity,
            balance_after=new_balance,
            reason=data.reason,
        )
        await self.repo.add(movement)
        # Avalia alerta de estoque baixo na mesma transação (produto já atualizado).
        await AlertService(self.session).evaluate(product)
        await self.session.commit()  # produto + movimento + alerta atômicos
        await self.session.refresh(movement)
        logger.info(
            "stock_movement",
            product_id=str(product.id),
            type=data.type.value,
            quantity=data.quantity,
            balance_after=new_balance,
            user_id=str(user_id),
        )
        MOVEMENTS_TOTAL.labels(type=data.type.value).inc()
        return movement

    async def get_product(self, product_id: uuid.UUID) -> Product:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError("Produto", product_id)
        return product

    async def history(
        self, filters: MovementFilter, params: PaginationParams
    ) -> Page[StockMovement]:
        kwargs = filters.model_dump(exclude_none=True)
        items = await self.repo.list_history(offset=params.offset, limit=params.limit, **kwargs)
        total = await self.repo.count_history(**kwargs)
        return Page.create(items, total, params)
