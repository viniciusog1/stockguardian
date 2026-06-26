"""Integração: dashboard de contadores gerais (com cache Redis)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _make_supplier(auth_client: AsyncClient) -> str:
    doc = str(uuid.uuid4().int)[:14]
    resp = await auth_client.post(f"{PREFIX}/suppliers", json={"name": "Forn", "document": doc})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_product(auth_client: AsyncClient, supplier_id: str, *, active: bool = True) -> str:
    sku = "P-" + uuid.uuid4().hex[:6]
    resp = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": sku, "name": "Prod", "supplier_id": supplier_id},
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    if not active:
        patch = await auth_client.patch(f"{PREFIX}/products/{pid}", json={"is_active": False})
        assert patch.status_code == 200, patch.text
    return pid


async def test_summary_counts(auth_client: AsyncClient) -> None:
    sid = await _make_supplier(auth_client)
    await _make_product(auth_client, sid, active=True)
    await _make_product(auth_client, sid, active=False)  # inativo não conta

    resp = await auth_client.get(f"{PREFIX}/dashboard/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active_products"] == 1
    assert body["active_suppliers"] == 1
    assert body["total_users"] >= 1  # admin do auth_client


async def test_summary_is_cached(auth_client: AsyncClient) -> None:
    sid = await _make_supplier(auth_client)
    await _make_product(auth_client, sid, active=True)

    first = (await auth_client.get(f"{PREFIX}/dashboard/summary")).json()
    assert first["active_products"] == 1

    # Cria outro produto; dentro do TTL o valor servido continua o cacheado.
    await _make_product(auth_client, sid, active=True)
    second = (await auth_client.get(f"{PREFIX}/dashboard/summary")).json()
    assert second["active_products"] == 1  # ainda do cache


async def test_requires_auth(client: AsyncClient) -> None:
    resp = await client.get(f"{PREFIX}/dashboard/summary")
    assert resp.status_code == 401
