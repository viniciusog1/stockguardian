from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductBase(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    min_stock: int = Field(default=0, ge=0)
    max_stock: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_stock_bounds(self) -> ProductBase:
        if self.max_stock is not None and self.max_stock < self.min_stock:
            raise ValueError("max_stock não pode ser menor que min_stock.")
        return self


class ProductCreate(ProductBase):
    supplier_id: uuid.UUID
    # Estoque inicial é definido por movimentação; produto nasce com quantity=0.


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    min_stock: int | None = Field(default=None, ge=0)
    max_stock: int | None = Field(default=None, ge=0)
    supplier_id: uuid.UUID | None = None
    is_active: bool | None = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quantity: int
    is_active: bool
    supplier_id: uuid.UUID
    is_low_stock: bool
    is_overstock: bool
    created_at: datetime
    updated_at: datetime
