from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class MovementType(StrEnum):
    IN = "in"  # entrada — soma ao estoque
    OUT = "out"  # saída — subtrai do estoque
    ADJUSTMENT = "adjustment"  # ajuste — define valor absoluto (inventário)


class StockMovement(UUIDMixin, TimestampMixin, Base):
    """Registro imutável de cada alteração de estoque (event sourcing simples).

    ``balance_after`` guarda o snapshot do estoque após a movimentação, evitando
    recomputar o histórico para reconstruir saldos.
    """

    __tablename__ = "stock_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    type: Mapped[MovementType] = mapped_column(
        # Persiste os valores ("in"/"out"/...) em vez dos nomes dos membros.
        SAEnum(
            MovementType,
            name="movement_type",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    product: Mapped[Product] = relationship(back_populates="movements")
    user: Mapped[User] = relationship(lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StockMovement {self.type} qty={self.quantity} bal={self.balance_after}>"
