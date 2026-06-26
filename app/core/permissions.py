"""Permissões nomeadas (RBAC granular).

Fonte única de verdade do que cada role pode fazer. As rotas checam permissões
(via `require_permission`), não roles diretamente.
"""

from __future__ import annotations

from enum import StrEnum

from app.models.user import UserRole


class Permission(StrEnum):
    SUPPLIER_READ = "supplier:read"
    SUPPLIER_WRITE = "supplier:write"
    PRODUCT_READ = "product:read"
    PRODUCT_WRITE = "product:write"
    MOVEMENT_READ = "movement:read"
    MOVEMENT_CREATE = "movement:create"
    ALERT_READ = "alert:read"
    ALERT_ACKNOWLEDGE = "alert:acknowledge"
    ALERT_RESOLVE = "alert:resolve"
    DASHBOARD_READ = "dashboard:read"
    USER_MANAGE = "user:manage"


_OPERATOR: frozenset[Permission] = frozenset(
    {
        Permission.SUPPLIER_READ,
        Permission.PRODUCT_READ,
        Permission.MOVEMENT_READ,
        Permission.MOVEMENT_CREATE,
        Permission.ALERT_READ,
        Permission.ALERT_ACKNOWLEDGE,
    }
)
_MANAGER: frozenset[Permission] = _OPERATOR | frozenset(
    {
        Permission.SUPPLIER_WRITE,
        Permission.PRODUCT_WRITE,
        Permission.ALERT_RESOLVE,
        Permission.DASHBOARD_READ,
    }
)
_ADMIN: frozenset[Permission] = frozenset(Permission)  # todas

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.OPERATOR: _OPERATOR,
    UserRole.MANAGER: _MANAGER,
    UserRole.ADMIN: _ADMIN,
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def has_permissions(role: UserRole, *perms: Permission) -> bool:
    granted = permissions_for(role)
    return all(p in granted for p in perms)
