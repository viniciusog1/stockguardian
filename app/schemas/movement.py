from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock_movement import MovementType


class MovementCreate(BaseModel):
    product_id: uuid.UUID
    type: MovementType
    quantity: int = Field(gt=0, description="Quantidade movimentada (sempre positiva).")
    reason: str | None = Field(default=None, max_length=255)


class MovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    user_id: uuid.UUID
    type: MovementType
    quantity: int
    balance_after: int
    reason: str | None
    created_at: datetime


class MovementFilter(BaseModel):
    """Filtros opcionais do histórico de movimentações."""

    product_id: uuid.UUID | None = None
    type: MovementType | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
