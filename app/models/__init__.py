"""Modelos SQLAlchemy.

Importados aqui para que o metadata da ``Base`` conheça todas as tabelas
(necessário para o autogenerate do Alembic).
"""

from app.models.base import Base
from app.models.product import Product
from app.models.stock_alert import ACTIVE_ALERT_STATUSES, AlertKind, AlertStatus, StockAlert
from app.models.stock_movement import MovementType, StockMovement
from app.models.supplier import Supplier
from app.models.user import User, UserRole

__all__ = [
    "ACTIVE_ALERT_STATUSES",
    "AlertKind",
    "AlertStatus",
    "Base",
    "MovementType",
    "Product",
    "StockAlert",
    "StockMovement",
    "Supplier",
    "User",
    "UserRole",
]
