"""Integração: relatórios operacionais (valuation + resumo de movimentações)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _supplier(auth_client: AsyncClient) -> str:
    doc = str(uuid.uuid4().int)[:14]
    resp = await auth_client.post(f"{PREFIX}/suppliers", json={"name": "Forn", "document": doc})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _product(
    auth_client: AsyncClient, supplier_id: str, *, unit_price: str, active: bool = True
) -> str:
    sku = "R-" + uuid.uuid4().hex[:6]
    resp = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": sku, "name": "Prod", "supplier_id": supplier_id, "unit_price": unit_price},
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    if not active:
        patch = await auth_client.patch(f"{PREFIX}/products/{pid}", json={"is_active": False})
        assert patch.status_code == 200, patch.text
    return pid


async def _move(auth_client: AsyncClient, pid: str, mtype: str, qty: int) -> None:
    resp = await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": mtype, "quantity": qty}
    )
    assert resp.status_code == 201, resp.text


async def test_inventory_valuation(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    p1 = await _product(auth_client, sid, unit_price="10.00")
    p2 = await _product(auth_client, sid, unit_price="2.50")
    await _move(auth_client, p1, "in", 5)  # 5 * 10.00 = 50.00
    await _move(auth_client, p2, "in", 4)  # 4 *  2.50 = 10.00

    resp = await auth_client.get(f"{PREFIX}/reports/inventory-valuation")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["total_products"] == 2
    assert body["summary"]["total_units"] == 9
    assert float(body["summary"]["total_value"]) == 60.0
    # ordenado por stock_value desc -> p1 primeiro
    assert body["items"][0]["product_id"] == p1
    assert float(body["items"][0]["stock_value"]) == 50.0


async def test_valuation_only_active_filter(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    active = await _product(auth_client, sid, unit_price="10.00")
    inactive = await _product(auth_client, sid, unit_price="10.00", active=False)
    await _move(auth_client, active, "in", 1)

    default_ids = [
        i["product_id"]
        for i in (await auth_client.get(f"{PREFIX}/reports/inventory-valuation")).json()["items"]
    ]
    assert active in default_ids and inactive not in default_ids

    all_ids = [
        i["product_id"]
        for i in (
            await auth_client.get(
                f"{PREFIX}/reports/inventory-valuation", params={"only_active": "false"}
            )
        ).json()["items"]
    ]
    assert inactive in all_ids


async def test_valuation_supplier_filter(auth_client: AsyncClient) -> None:
    s1 = await _supplier(auth_client)
    s2 = await _supplier(auth_client)
    p1 = await _product(auth_client, s1, unit_price="10.00")
    await _product(auth_client, s2, unit_price="10.00")
    await _move(auth_client, p1, "in", 1)

    body = (
        await auth_client.get(f"{PREFIX}/reports/inventory-valuation", params={"supplier_id": s1})
    ).json()
    assert [i["product_id"] for i in body["items"]] == [p1]


async def test_movements_summary(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    pid = await _product(auth_client, sid, unit_price="1.00")
    await _move(auth_client, pid, "in", 10)
    await _move(auth_client, pid, "in", 5)
    await _move(auth_client, pid, "out", 3)

    body = (
        await auth_client.get(f"{PREFIX}/reports/movements-summary", params={"product_id": pid})
    ).json()
    by_type = {r["type"]: r for r in body["rows"]}
    assert by_type["in"]["movement_count"] == 2
    assert by_type["in"]["total_quantity"] == 15
    assert by_type["out"]["movement_count"] == 1
    assert by_type["out"]["total_quantity"] == 3
    assert by_type["adjustment"]["movement_count"] == 0
    assert by_type["adjustment"]["total_quantity"] == 0
    assert body["total_movements"] == 3


async def test_movements_summary_future_window_is_empty(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    pid = await _product(auth_client, sid, unit_price="1.00")
    await _move(auth_client, pid, "in", 10)

    body = (
        await auth_client.get(
            f"{PREFIX}/reports/movements-summary",
            params={"product_id": pid, "date_from": "2999-01-01T00:00:00Z"},
        )
    ).json()
    assert body["total_movements"] == 0
    assert all(r["movement_count"] == 0 for r in body["rows"])


async def test_reports_require_auth(client: AsyncClient) -> None:
    assert (await client.get(f"{PREFIX}/reports/inventory-valuation")).status_code == 401
    assert (await client.get(f"{PREFIX}/reports/movements-summary")).status_code == 401
