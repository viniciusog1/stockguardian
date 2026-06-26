"""Integração: autorização granular por permissão."""

from __future__ import annotations

import uuid

import pytest
from app.models.product import Product
from app.models.stock_alert import AlertStatus, StockAlert
from app.models.supplier import Supplier
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _seed_product(db_session: AsyncSession) -> uuid.UUID:
    sup = Supplier(name="Forn", document="11222333000181")
    db_session.add(sup)
    await db_session.flush()
    prod = Product(sku="P-RBAC", name="Produto", supplier_id=sup.id, quantity=0, min_stock=0)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(prod)
    return prod.id


async def _seed_open_alert(db_session: AsyncSession, product_id: uuid.UUID) -> uuid.UUID:
    alert = StockAlert(
        product_id=product_id,
        status=AlertStatus.OPEN,
        triggered_quantity=0,
        min_stock_at_trigger=5,
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    return alert.id


async def test_me_returns_permissions(operator_client: AsyncClient) -> None:
    resp = await operator_client.get(f"{PREFIX}/auth/me")
    assert resp.status_code == 200, resp.text
    perms = resp.json()["permissions"]
    assert "movement:create" in perms
    assert "product:write" not in perms


async def test_operator_cannot_create_product(operator_client: AsyncClient) -> None:
    resp = await operator_client.post(
        f"{PREFIX}/products",
        json={"sku": "X1", "name": "Nope", "supplier_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    body = resp.json()["error"]
    assert body["code"] == "authorization_error"
    assert "product:write" in body["details"]["required"]


async def test_operator_can_create_movement(
    operator_client: AsyncClient, db_session: AsyncSession
) -> None:
    pid = await _seed_product(db_session)
    resp = await operator_client.post(
        f"{PREFIX}/movements",
        json={"product_id": str(pid), "type": "in", "quantity": 5},
    )
    assert resp.status_code == 201, resp.text


async def test_operator_acknowledge_but_not_resolve(
    operator_client: AsyncClient, db_session: AsyncSession
) -> None:
    pid = await _seed_product(db_session)
    aid = await _seed_open_alert(db_session, pid)

    ack = await operator_client.post(f"{PREFIX}/alerts/{aid}/acknowledge")
    assert ack.status_code == 200, ack.text

    res = await operator_client.post(f"{PREFIX}/alerts/{aid}/resolve")
    assert res.status_code == 403


async def test_manager_can_create_product(
    manager_client: AsyncClient, db_session: AsyncSession
) -> None:
    sup = Supplier(name="Forn", document="11222333000181")
    db_session.add(sup)
    await db_session.commit()
    await db_session.refresh(sup)
    resp = await manager_client.post(
        f"{PREFIX}/products",
        json={"sku": "M1", "name": "Prod Manager", "supplier_id": str(sup.id)},
    )
    assert resp.status_code == 201, resp.text


async def test_manager_cannot_manage_users(manager_client: AsyncClient) -> None:
    resp = await manager_client.post(
        f"{PREFIX}/users",
        json={"email": "n@test.com", "password": "Pw@123456", "full_name": "Nome"},
    )
    assert resp.status_code == 403


async def test_admin_can_manage_users(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        f"{PREFIX}/users",
        json={"email": "novo@test.com", "password": "Pw@123456", "full_name": "Novo User"},
    )
    assert resp.status_code == 201, resp.text
