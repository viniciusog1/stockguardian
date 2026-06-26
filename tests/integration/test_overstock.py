"""Integração: detecção de superestoque (alertas kind=overstock)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _make_product(auth_client: AsyncClient, *, min_stock: int, max_stock: int) -> str:
    sup = await auth_client.post(
        f"{PREFIX}/suppliers", json={"name": "Forn", "document": "11222333000181"}
    )
    sid = sup.json()["id"]
    prod = await auth_client.post(
        f"{PREFIX}/products",
        json={
            "sku": "OV-1",
            "name": "Produto Over",
            "supplier_id": sid,
            "min_stock": min_stock,
            "max_stock": max_stock,
        },
    )
    assert prod.status_code == 201, prod.text
    return prod.json()["id"]


async def test_overstock_opens_and_resolves(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=0, max_stock=10)

    # entra acima do máximo -> abre overstock
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 15}
    )
    resp = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid}
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["kind"] == "overstock"
    assert body["items"][0]["threshold_at_trigger"] == 10

    # sai voltando para <= máximo -> resolve
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "out", "quantity": 8}
    )
    resp = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid}
    )
    statuses = [a["status"] for a in resp.json()["items"]]
    assert statuses == ["resolved"]


async def test_low_and_overstock_independent(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=5, max_stock=10)

    # vai a 15 -> overstock aberto, sem low
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 15}
    )
    over = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid}
    )
    assert over.json()["total"] == 1
    low = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "low_stock", "status": "open", "product_id": pid}
    )
    assert low.json()["total"] == 0

    # cai a 2 (<=5) -> overstock resolve, low abre
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "out", "quantity": 13}
    )
    over_open = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "overstock", "status": "open", "product_id": pid}
    )
    assert over_open.json()["total"] == 0
    low_open = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "low_stock", "status": "open", "product_id": pid}
    )
    assert low_open.json()["total"] == 1


async def test_no_overstock_without_max_stock(auth_client: AsyncClient) -> None:
    sup = await auth_client.post(
        f"{PREFIX}/suppliers", json={"name": "Forn", "document": "11222333000181"}
    )
    sid = sup.json()["id"]
    prod = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": "NOMAX", "name": "Sem max", "supplier_id": sid, "min_stock": 0},
    )
    pid = prod.json()["id"]
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 9999}
    )
    resp = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid}
    )
    assert resp.json()["total"] == 0
