"""Integração: endpoint /metrics (Prometheus)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def test_metrics_open_and_lists_names(client: AsyncClient) -> None:
    resp = await client.get("/metrics")  # sem auth
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "stockguardian_movements_total" in body
    assert "http_request" in body


async def test_movement_increments_counter(auth_client: AsyncClient) -> None:
    doc = str(uuid.uuid4().int)[:14]
    sid = (
        await auth_client.post(f"{PREFIX}/suppliers", json={"name": "Forn", "document": doc})
    ).json()["id"]
    pid = (
        await auth_client.post(
            f"{PREFIX}/products",
            json={"sku": "M-" + uuid.uuid4().hex[:6], "name": "Prod", "supplier_id": sid},
        )
    ).json()["id"]
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 3}
    )

    body = (await auth_client.get("/metrics")).text
    assert 'stockguardian_movements_total{type="in"}' in body
