from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# Estados que contam como "alerta ativo" (não-resolvido).
ACTIVE_ALERT_STATUSES = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)


class StockAlert(UUIDMixin, TimestampMixin, Base):
    """Alerta de estoque baixo de um produto.

    Gerado automaticamente quando o estoque cruza o mínimo. Snapshots
    (`triggered_quantity`, `min_stock_at_trigger`) preservam o contexto da
    abertura para auditoria.
    """

    __tablename__ = "stock_alerts"
    __table_args__ = (
        # Dedup: no máximo 1 alerta não-resolvido por produto (imposto pelo banco).
        Index(
            "uq_stock_alerts_active_per_product",
            "product_id",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(
            AlertStatus,
            name="alert_status",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AlertStatus.OPEN,
        nullable=False,
    )
    triggered_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    min_stock_at_trigger: Mapped[int] = mapped_column(Integer, nullable=False)

    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped[Product] = relationship(back_populates="alerts")
    acknowledger: Mapped[User | None] = relationship(lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StockAlert {self.status} product={self.product_id}>"
