from __future__ import annotations

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    active_products: int
    active_suppliers: int
    total_users: int
