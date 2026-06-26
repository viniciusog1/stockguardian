"""Teste de integração do fluxo de estoque ponta a ponta.

Fornecedor → Produto → movimentações (IN/OUT) e a regra de estoque insuficiente.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _create_product(auth_client: AsyncClient) -> str:
    supplier = await auth_client.post(
        f"{PREFIX}/suppliers",
        json={"name": "Fornecedor X", "document": "12345678000199"},
    )
    assert supplier.status_code == 201, supplier.text
    supplier_id = supplier.json()["id"]

    product = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": "SKU-TEST", "name": "Produto Teste", "supplier_id": supplier_id},
    )
    assert product.status_code == 201, product.text
    assert product.json()["quantity"] == 0
    return product.json()["id"]


async def test_full_stock_flow(auth_client: AsyncClient) -> None:
    product_id = await _create_product(auth_client)

    # Entrada de 50
    resp = await auth_client.post(
        f"{PREFIX}/movements",
        json={"product_id": product_id, "type": "in", "quantity": 50},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["balance_after"] == 50

    # Saída de 60 -> estoque insuficiente
    resp = await auth_client.post(
        f"{PREFIX}/movements",
        json={"product_id": product_id, "type": "out", "quantity": 60},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "insufficient_stock"

    # Saída de 30 -> saldo 20
    resp = await auth_client.post(
        f"{PREFIX}/movements",
        json={"product_id": product_id, "type": "out", "quantity": 30},
    )
    assert resp.status_code == 201
    assert resp.json()["balance_after"] == 20

    # Produto reflete o saldo
    resp = await auth_client.get(f"{PREFIX}/products/{product_id}")
    assert resp.json()["quantity"] == 20

    # Histórico tem 2 movimentos (a saída de 60 falhou)
    resp = await auth_client.get(f"{PREFIX}/movements", params={"product_id": product_id})
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["balance_after"] == 20  # mais recente primeiro


async def test_adjustment_sets_absolute(auth_client: AsyncClient) -> None:
    product_id = await _create_product(auth_client)
    await auth_client.post(
        f"{PREFIX}/movements",
        json={"product_id": product_id, "type": "in", "quantity": 100},
    )
    resp = await auth_client.post(
        f"{PREFIX}/movements",
        json={
            "product_id": product_id,
            "type": "adjustment",
            "quantity": 7,
            "reason": "inventário",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["balance_after"] == 7


async def test_duplicate_sku_conflict(auth_client: AsyncClient) -> None:
    await _create_product(auth_client)
    supplier = await auth_client.get(f"{PREFIX}/suppliers")
    supplier_id = supplier.json()["items"][0]["id"]
    resp = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": "SKU-TEST", "name": "Outro", "supplier_id": supplier_id},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
