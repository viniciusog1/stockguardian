from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Row, Select, func, select

from app.models.stock_movement import MovementType, StockMovement
from app.repositories.base import BaseRepository


class MovementRepository(BaseRepository[StockMovement]):
    model = StockMovement

    def _filtered_stmt(
        self,
        *,
        product_id: uuid.UUID | None = None,
        type: MovementType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Select[tuple[StockMovement]]:
        stmt = select(StockMovement)
        if product_id is not None:
            stmt = stmt.where(StockMovement.product_id == product_id)
        if type is not None:
            stmt = stmt.where(StockMovement.type == type)
        if date_from is not None:
            stmt = stmt.where(StockMovement.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(StockMovement.created_at <= date_to)
        return stmt

    async def list_history(
        self,
        *,
        offset: int,
        limit: int,
        product_id: uuid.UUID | None = None,
        type: MovementType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[StockMovement]:
        stmt = self._filtered_stmt(
            product_id=product_id, type=type, date_from=date_from, date_to=date_to
        )
        stmt = stmt.order_by(StockMovement.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_history(
        self,
        *,
        product_id: uuid.UUID | None = None,
        type: MovementType | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        base = self._filtered_stmt(
            product_id=product_id, type=type, date_from=date_from, date_to=date_to
        ).subquery()
        result = await self.session.execute(select(func.count()).select_from(base))
        return int(result.scalar_one())

    async def summary_by_type(
        self,
        *,
        product_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[Row[tuple[MovementType, int, int]]]:
        """Agrega contagem e soma de quantidade por tipo de movimentação no período."""
        stmt = select(
            StockMovement.type,
            func.count().label("movement_count"),
            func.coalesce(func.sum(StockMovement.quantity), 0).label("total_quantity"),
        ).group_by(StockMovement.type)
        if product_id is not None:
            stmt = stmt.where(StockMovement.product_id == product_id)
        if date_from is not None:
            stmt = stmt.where(StockMovement.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(StockMovement.created_at <= date_to)
        result = await self.session.execute(stmt)
        return result.all()
