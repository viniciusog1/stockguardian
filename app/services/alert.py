"""Serviço de alertas de estoque baixo.

A função pura `decide_alert_action` concentra a regra; `AlertService` orquestra
persistência, transação e log. `evaluate` é chamado por outros serviços (dentro
da transação deles) após mutarem o estoque de um produto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.exceptions.domain import ConflictError, NotFoundError
from app.models.product import Product
from app.models.stock_alert import AlertStatus, StockAlert
from app.repositories.alert import AlertRepository
from app.schemas.alert import AlertFilter
from app.schemas.common import Page, PaginationParams

logger = get_logger(__name__)


class AlertAction(StrEnum):
    OPEN = "open"
    RESOLVE = "resolve"
    NOOP = "noop"


def decide_alert_action(*, quantity: int, min_stock: int, has_active: bool) -> AlertAction:
    """Decide o que fazer com o alerta de um produto.

    - estoque <= mínimo e sem alerta ativo -> abrir
    - estoque > mínimo e com alerta ativo -> resolver
    - caso contrário -> nada (idempotente)
    """
    is_low = quantity <= min_stock
    if is_low and not has_active:
        return AlertAction.OPEN
    if not is_low and has_active:
        return AlertAction.RESOLVE
    return AlertAction.NOOP


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AlertRepository(session)

    async def evaluate(self, product: Product) -> StockAlert | None:
        """Abre ou resolve alerta conforme o estoque do produto.

        Faz flush (não commit) — quem orquestra a transação commita.
        """
        active = await self.repo.get_active_for_product(product.id)
        action = decide_alert_action(
            quantity=product.quantity,
            min_stock=product.min_stock,
            has_active=active is not None,
        )
        if action is AlertAction.OPEN:
            alert = StockAlert(
                product_id=product.id,
                status=AlertStatus.OPEN,
                triggered_quantity=product.quantity,
                min_stock_at_trigger=product.min_stock,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(alert)
                    await self.session.flush()
            except IntegrityError:
                # Corrida: outro caminho abriu o alerta primeiro. Idempotente.
                return None
            logger.info(
                "alert_opened",
                alert_id=str(alert.id),
                product_id=str(product.id),
                quantity=product.quantity,
                min_stock=product.min_stock,
            )
            return alert
        if action is AlertAction.RESOLVE and active is not None:
            active.status = AlertStatus.RESOLVED
            active.resolved_at = datetime.now(UTC)
            await self.session.flush()
            logger.info(
                "alert_resolved",
                alert_id=str(active.id),
                product_id=str(product.id),
                quantity=product.quantity,
            )
            return active
        return None

    async def get(self, alert_id: uuid.UUID) -> StockAlert:
        alert = await self.repo.get(alert_id)
        if alert is None:
            raise NotFoundError("Alerta", alert_id)
        return alert

    async def list(self, filters: AlertFilter, params: PaginationParams) -> Page[StockAlert]:
        kwargs = filters.model_dump(exclude_none=True)
        items = await self.repo.list_filtered(offset=params.offset, limit=params.limit, **kwargs)
        total = await self.repo.count_filtered(**kwargs)
        return Page.create(items, total, params)

    async def acknowledge(self, alert_id: uuid.UUID, user_id: uuid.UUID) -> StockAlert:
        alert = await self.get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise ConflictError("Alerta já resolvido não pode ser reconhecido.")
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def resolve(self, alert_id: uuid.UUID) -> StockAlert:
        alert = await self.get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise ConflictError("Alerta já está resolvido.")
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(alert)
        return alert
