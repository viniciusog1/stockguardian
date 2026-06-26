"""Serviço de relatórios operacionais (read-only).

Orquestra agregações dos repositórios e monta os relatórios. O SQL fica nos
repositórios; aqui ficam composição e normalização.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_movement import MovementType
from app.repositories.movement import MovementRepository
from app.repositories.product import ProductRepository
from app.schemas.report import (
    InventoryValuationItem,
    InventoryValuationReport,
    InventoryValuationSummary,
    MovementsSummaryReport,
    MovementsSummaryRow,
)


def build_movement_summary_rows(
    counts: dict[MovementType, tuple[int, int]],
) -> list[MovementsSummaryRow]:
    """Uma linha por MovementType (ordem do enum), com zeros quando o tipo faltou."""
    return [
        MovementsSummaryRow(
            type=mtype,
            movement_count=counts.get(mtype, (0, 0))[0],
            total_quantity=counts.get(mtype, (0, 0))[1],
        )
        for mtype in MovementType
    ]


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def inventory_valuation(
        self, *, supplier_id: uuid.UUID | None = None, only_active: bool = True
    ) -> InventoryValuationReport:
        rows = await ProductRepository(self.session).inventory_valuation(
            supplier_id=supplier_id, only_active=only_active
        )
        items = [
            InventoryValuationItem(
                product_id=row.id,
                sku=row.sku,
                name=row.name,
                quantity=row.quantity,
                unit_price=row.unit_price,
                stock_value=row.stock_value,
            )
            for row in rows
        ]
        summary = InventoryValuationSummary(
            total_products=len(items),
            total_units=sum(i.quantity for i in items),
            total_value=sum((i.stock_value for i in items), Decimal("0.00")),
        )
        return InventoryValuationReport(
            generated_at=datetime.now(UTC), summary=summary, items=items
        )

    async def movements_summary(
        self,
        *,
        product_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> MovementsSummaryReport:
        raw = await MovementRepository(self.session).summary_by_type(
            product_id=product_id, date_from=date_from, date_to=date_to
        )
        counts = {row.type: (row.movement_count, row.total_quantity) for row in raw}
        rows = build_movement_summary_rows(counts)
        return MovementsSummaryReport(
            generated_at=datetime.now(UTC),
            date_from=date_from,
            date_to=date_to,
            rows=rows,
            total_movements=sum(r.movement_count for r in rows),
        )
