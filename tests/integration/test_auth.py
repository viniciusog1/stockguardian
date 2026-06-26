"""Testes de integração do fluxo de autenticação (JWT real + fakeredis)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def test_register_login_me_flow(client: AsyncClient) -> None:
    # Registro
    resp = await client.post(
        f"{PREFIX}/auth/register",
        json={"email": "joao@test.com", "password": "Senha@123", "full_name": "João"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "joao@test.com"

    # Login
    resp = await client.post(
        f"{PREFIX}/auth/login",
        json={"email": "joao@test.com", "password": "Senha@123"},
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    # /me com bearer
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    resp = await client.get(f"{PREFIX}/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "João"


async def test_duplicate_email_conflict(client: AsyncClient) -> None:
    payload = {"email": "dup@test.com", "password": "Senha@123", "full_name": "Dup"}
    assert (await client.post(f"{PREFIX}/auth/register", json=payload)).status_code == 201
    resp = await client.post(f"{PREFIX}/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        f"{PREFIX}/auth/register",
        json={"email": "x@test.com", "password": "Senha@123", "full_name": "Xavier"},
    )
    resp = await client.post(
        f"{PREFIX}/auth/login", json={"email": "x@test.com", "password": "errada"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "authentication_error"


async def test_refresh_rotates_and_revokes_old(client: AsyncClient) -> None:
    await client.post(
        f"{PREFIX}/auth/register",
        json={"email": "r@test.com", "password": "Senha@123", "full_name": "Refresh User"},
    )
    login = await client.post(
        f"{PREFIX}/auth/login", json={"email": "r@test.com", "password": "Senha@123"}
    )
    old_refresh = login.json()["refresh_token"]

    # Refresh válido
    resp = await client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200

    # Reuso do refresh antigo -> revogado
    resp = await client.post(f"{PREFIX}/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401


async def test_protected_route_requires_token(client: AsyncClient) -> None:
    resp = await client.get(f"{PREFIX}/auth/me")
    assert resp.status_code == 401
