from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.stock_movement import MovementType


class InventoryValuationItem(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    stock_value: Decimal


class InventoryValuationSummary(BaseModel):
    total_products: int
    total_units: int
    total_value: Decimal


class InventoryValuationReport(BaseModel):
    generated_at: datetime
    summary: InventoryValuationSummary
    items: list[InventoryValuationItem]


class MovementsSummaryRow(BaseModel):
    type: MovementType
    movement_count: int
    total_quantity: int


class MovementsSummaryReport(BaseModel):
    generated_at: datetime
    date_from: datetime | None
    date_to: datetime | None
    rows: list[MovementsSummaryRow]
    total_movements: int
