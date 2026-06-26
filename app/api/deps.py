"""Re-export das dependências mais usadas, para imports curtos nas rotas."""

from __future__ import annotations

from app.dependencies.auth import CurrentUser, get_current_active_user, require_permission
from app.dependencies.db import DBSession, RedisClient
from app.utils.pagination import Pagination

__all__ = [
    "CurrentUser",
    "DBSession",
    "Pagination",
    "RedisClient",
    "get_current_active_user",
    "require_permission",
]
