"""Testes unitários do mapa de permissões (dado puro)."""

from __future__ import annotations

import pytest
from app.core.permissions import Permission, has_permissions, permissions_for
from app.models.user import UserRole

pytestmark = pytest.mark.unit


def test_admin_has_all_permissions() -> None:
    assert permissions_for(UserRole.ADMIN) == frozenset(Permission)


def test_operator_subset() -> None:
    perms = permissions_for(UserRole.OPERATOR)
    assert Permission.MOVEMENT_CREATE in perms
    assert Permission.ALERT_ACKNOWLEDGE in perms
    assert Permission.PRODUCT_WRITE not in perms
    assert Permission.ALERT_RESOLVE not in perms
    assert Permission.USER_MANAGE not in perms


def test_manager_has_writes_but_not_user_manage() -> None:
    perms = permissions_for(UserRole.MANAGER)
    assert Permission.PRODUCT_WRITE in perms
    assert Permission.ALERT_RESOLVE in perms
    assert Permission.DASHBOARD_READ in perms
    assert Permission.USER_MANAGE not in perms


def test_has_permissions_helper() -> None:
    assert has_permissions(UserRole.MANAGER, Permission.PRODUCT_WRITE)
    assert has_permissions(
        UserRole.OPERATOR, Permission.MOVEMENT_CREATE, Permission.ALERT_ACKNOWLEDGE
    )
    assert not has_permissions(UserRole.OPERATOR, Permission.PRODUCT_WRITE)
