"""Dependências de autenticação e autorização.

Decodifica o access token, carrega o usuário e expõe um factory ``require_role``
para proteger rotas por papel (RBAC simples).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.core.config import settings
from app.core.security import TokenType, decode_token
from app.dependencies.db import DBSession
from app.exceptions.domain import AuthenticationError, AuthorizationError
from app.models.user import User, UserRole
from app.repositories.user import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login/form")

Token = Annotated[str, Depends(oauth2_scheme)]


async def get_current_user(token: Token, session: DBSession) -> User:
    try:
        payload = decode_token(token, TokenType.ACCESS)
    except JWTError as exc:
        raise AuthenticationError("Token inválido ou expirado.") from exc

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Token sem subject.")

    user = await UserRepository(session).get(user_id)
    if user is None:
        raise AuthenticationError("Usuário não encontrado.")
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise AuthenticationError("Usuário inativo.")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_active_user)]


def require_role(*allowed: UserRole) -> Callable[[User], Awaitable[User]]:
    """Factory de dependência que exige um dos papéis informados.

    ADMIN é sempre autorizado (superusuário).
    """

    async def _checker(current_user: CurrentUser) -> User:
        if current_user.role is UserRole.ADMIN or current_user.role in allowed:
            return current_user
        raise AuthorizationError(
            "Permissão insuficiente para esta operação.",
            details={"required": [r.value for r in allowed]},
        )

    return _checker
