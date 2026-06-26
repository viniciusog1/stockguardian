from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.stock_movement import StockMovement
    from app.models.supplier import Supplier


class Product(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_product_quantity_non_negative"),
        CheckConstraint("min_stock >= 0", name="ck_product_min_stock_non_negative"),
        CheckConstraint(
            "max_stock IS NULL OR max_stock >= min_stock",
            name="ck_product_max_ge_min",
        ),
    )

    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )

    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    supplier: Mapped[Supplier] = relationship(back_populates="products", lazy="selectin")
    movements: Mapped[list[StockMovement]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

    @property
    def is_low_stock(self) -> bool:
        """True quando o estoque atingiu/cruzou o mínimo (usado em alertas na Fase 2)."""
        return self.quantity <= self.min_stock

    @property
    def is_overstock(self) -> bool:
        """True quando ultrapassa o máximo configurado (base p/ Fase 3)."""
        return self.max_stock is not None and self.quantity > self.max_stock

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product {self.sku} qty={self.quantity}>"
