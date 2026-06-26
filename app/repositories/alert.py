from __future__ import annotations

import uuid

from sqlalchemy import Select, func, select

from app.models.stock_alert import ACTIVE_ALERT_STATUSES, AlertKind, AlertStatus, StockAlert
from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[StockAlert]):
    model = StockAlert

    async def get_active_for_product(
        self, product_id: uuid.UUID, kind: AlertKind
    ) -> StockAlert | None:
        """Retorna o alerta não-resolvido do produto para o tipo dado (dedup)."""
        stmt = (
            select(StockAlert)
            .where(StockAlert.product_id == product_id)
            .where(StockAlert.kind == kind)
            .where(StockAlert.status.in_(ACTIVE_ALERT_STATUSES))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _filtered_stmt(
        self,
        *,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        product_id: uuid.UUID | None = None,
    ) -> Select[tuple[StockAlert]]:
        stmt = select(StockAlert)
        if status is not None:
            stmt = stmt.where(StockAlert.status == status)
        if kind is not None:
            stmt = stmt.where(StockAlert.kind == kind)
        if product_id is not None:
            stmt = stmt.where(StockAlert.product_id == product_id)
        return stmt

    async def list_filtered(
        self,
        *,
        offset: int,
        limit: int,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[StockAlert]:
        stmt = self._filtered_stmt(status=status, kind=kind, product_id=product_id)
        stmt = stmt.order_by(StockAlert.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        product_id: uuid.UUID | None = None,
    ) -> int:
        base = self._filtered_stmt(status=status, kind=kind, product_id=product_id).subquery()
        result = await self.session.execute(select(func.count()).select_from(base))
        return int(result.scalar_one())
