from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.stock_alert import AlertKind, AlertStatus


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    kind: AlertKind
    status: AlertStatus
    triggered_quantity: int
    threshold_at_trigger: int
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertFilter(BaseModel):
    """Filtros opcionais da listagem de alertas."""

    status: AlertStatus | None = None
    kind: AlertKind | None = None
    product_id: uuid.UUID | None = None
