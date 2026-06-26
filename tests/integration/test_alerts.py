"""Integração: ciclo de vida dos alertas de estoque baixo."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _make_product(auth_client: AsyncClient, *, min_stock: int = 10) -> str:
    sup = await auth_client.post(
        f"{PREFIX}/suppliers", json={"name": "Forn", "document": "11222333000181"}
    )
    sid = sup.json()["id"]
    prod = await auth_client.post(
        f"{PREFIX}/products",
        json={
            "sku": "AL-1",
            "name": "Produto Alerta",
            "supplier_id": sid,
            "min_stock": min_stock,
        },
    )
    assert prod.status_code == 201, prod.text
    return prod.json()["id"]


async def test_out_below_minimum_opens_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 8}
    )  # 8 <= 10 já abre
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"status": "open"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["product_id"] == pid
    assert body["items"][0]["triggered_quantity"] == 8


async def test_recover_stock_resolves_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )  # abre
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 20}
    )  # 25 > 10 -> resolve
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid})
    statuses = [a["status"] for a in resp.json()["items"]]
    assert statuses == ["resolved"]


async def test_no_duplicate_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "out", "quantity": 2}
    )  # ainda baixo, não duplica
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid})
    assert resp.json()["total"] == 1


async def test_raising_min_stock_opens_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=1)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )  # 5 > 1, sem alerta
    assert (await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid})).json()[
        "total"
    ] == 0
    await auth_client.patch(f"{PREFIX}/products/{pid}", json={"min_stock": 10})  # 5 <= 10 -> abre
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid, "status": "open"})
    assert resp.json()["total"] == 1


async def test_acknowledge_and_resolve(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )
    alert_id = (await auth_client.get(f"{PREFIX}/alerts")).json()["items"][0]["id"]

    ack = await auth_client.post(f"{PREFIX}/alerts/{alert_id}/acknowledge")
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"
    assert ack.json()["acknowledged_by"] is not None

    res = await auth_client.post(f"{PREFIX}/alerts/{alert_id}/resolve")
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"

    # resolver de novo -> conflito
    again = await auth_client.post(f"{PREFIX}/alerts/{alert_id}/resolve")
    assert again.status_code == 409
