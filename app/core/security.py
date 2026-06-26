"""Primitivas de segurança: hashing de senha e tokens JWT.

Sem dependências do domínio/banco — apenas criptografia pura, fácil de testar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt opera sobre no máximo 72 bytes; truncamos explicitamente para evitar
# erro com senhas longas (comportamento consistente com a maioria dos sistemas).
_BCRYPT_MAX_BYTES = 72


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


# ----------------------------- Senhas -----------------------------------------


def hash_password(plain: str) -> str:
    pwd = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pwd = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(pwd, hashed.encode("utf-8"))
    except ValueError:
        return False


# ----------------------------- Tokens JWT -------------------------------------


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Cria um JWT assinado. Retorna ``(token, jti)``.

    O ``jti`` (JWT ID) identifica unicamente o token — usado para revogação de
    refresh tokens no Redis.
    """
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "jti": jti,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def create_access_token(
    subject: str, extra_claims: dict[str, Any] | None = None
) -> tuple[str, str]:
    return _create_token(
        subject,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def create_refresh_token(subject: str) -> tuple[str, str]:
    return _create_token(
        subject,
        TokenType.REFRESH,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decodifica e valida o token.

    Raises:
        JWTError: assinatura inválida, expirado, ou ``type`` divergente.
    """
    payload: dict[str, Any] = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("type") != expected_type.value:
        raise JWTError(f"Tipo de token inválido: esperado {expected_type.value}")
    return payload
