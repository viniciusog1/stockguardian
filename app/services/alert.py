"""Serviço de alertas de estoque (baixo e superestoque).

A função pura `decide_alert_action` concentra a regra; `AlertService` orquestra
persistência, transação e log. `evaluate` é chamado por outros serviços (dentro
da transação deles) após mutarem o estoque de um produto, avaliando os dois
tipos de alerta.
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
from app.models.stock_alert import AlertKind, AlertStatus, StockAlert
from app.repositories.alert import AlertRepository
from app.schemas.alert import AlertFilter
from app.schemas.common import Page, PaginationParams

logger = get_logger(__name__)


class AlertAction(StrEnum):
    OPEN = "open"
    RESOLVE = "resolve"
    NOOP = "noop"


def decide_alert_action(*, condition_met: bool, has_active: bool) -> AlertAction:
    """Decide o que fazer com o alerta de um produto para um tipo.

    - condição presente e sem alerta ativo -> abrir
    - condição ausente e com alerta ativo -> resolver
    - caso contrário -> nada (idempotente)
    """
    if condition_met and not has_active:
        return AlertAction.OPEN
    if not condition_met and has_active:
        return AlertAction.RESOLVE
    return AlertAction.NOOP


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AlertRepository(session)

    async def evaluate(self, product: Product) -> None:
        """Abre/resolve alertas de estoque baixo e superestoque do produto.

        Faz flush (não commit) — quem orquestra a transação commita.
        """
        checks: list[tuple[AlertKind, bool, int | None]] = [
            (AlertKind.LOW_STOCK, product.quantity <= product.min_stock, product.min_stock),
            (AlertKind.OVERSTOCK, product.is_overstock, product.max_stock),
        ]
        for kind, condition, threshold in checks:
            active = await self.repo.get_active_for_product(product.id, kind)
            action = decide_alert_action(condition_met=condition, has_active=active is not None)
            if action is AlertAction.OPEN:
                # condição verdadeira garante limite definido
                assert threshold is not None
                alert = StockAlert(
                    product_id=product.id,
                    kind=kind,
                    status=AlertStatus.OPEN,
                    triggered_quantity=product.quantity,
                    threshold_at_trigger=threshold,
                )
                try:
                    async with self.session.begin_nested():
                        self.session.add(alert)
                        await self.session.flush()
                except IntegrityError:
                    continue  # corrida: outro caminho abriu primeiro
                logger.info(
                    "alert_opened",
                    alert_id=str(alert.id),
                    product_id=str(product.id),
                    kind=kind.value,
                    quantity=product.quantity,
                    threshold=threshold,
                )
            elif action is AlertAction.RESOLVE and active is not None:
                active.status = AlertStatus.RESOLVED
                active.resolved_at = datetime.now(UTC)
                await self.session.flush()
                logger.info(
                    "alert_resolved",
                    alert_id=str(active.id),
                    product_id=str(product.id),
                    kind=kind.value,
                    quantity=product.quantity,
                )

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
