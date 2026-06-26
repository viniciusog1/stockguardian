"""Testes unitários das primitivas de segurança (sem I/O)."""

from __future__ import annotations

import pytest
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from jose import JWTError

pytestmark = pytest.mark.unit


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("S3nh@Forte")
    assert hashed != "S3nh@Forte"
    assert verify_password("S3nh@Forte", hashed)
    assert not verify_password("errada", hashed)


def test_access_token_encode_decode() -> None:
    token, jti = create_access_token("user-123", {"role": "admin"})
    payload = decode_token(token, TokenType.ACCESS)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    assert payload["jti"] == jti
    assert payload["type"] == "access"


def test_decode_rejects_wrong_token_type() -> None:
    refresh, _ = create_refresh_token("user-123")
    with pytest.raises(JWTError):
        decode_token(refresh, TokenType.ACCESS)


def test_decode_rejects_tampered_token() -> None:
    token, _ = create_access_token("user-123")
    with pytest.raises(JWTError):
        decode_token(token + "tamper", TokenType.ACCESS)
