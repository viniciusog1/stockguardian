"""Serviço de autenticação: registro, login, refresh e logout.

Os refresh tokens são rastreados no Redis por ``jti`` (whitelist). Isso permite
revogação imediata no logout e rotação de tokens — um access token roubado
expira rápido e o refresh pode ser invalidado a qualquer momento.
"""

from __future__ import annotations

from datetime import timedelta

from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.exceptions.domain import AuthenticationError, ConflictError
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest, TokenPair

logger = get_logger(__name__)


def _refresh_key(user_id: str, jti: str) -> str:
    return f"refresh:{user_id}:{jti}"


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis
        self.users = UserRepository(session)

    async def register(self, data: RegisterRequest) -> User:
        if await self.users.get_by_email(data.email):
            raise ConflictError("E-mail já cadastrado.", details={"field": "email"})
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
        )
        await self.users.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            # Mensagem genérica: não revela se o e-mail existe.
            raise AuthenticationError("Credenciais inválidas.")
        if not user.is_active:
            raise AuthenticationError("Usuário inativo.")
        return user

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.authenticate(email, password)
        return await self._issue_token_pair(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except JWTError as exc:
            raise AuthenticationError("Refresh token inválido ou expirado.") from exc

        user_id = payload["sub"]
        jti = payload["jti"]
        if not await self.redis.exists(_refresh_key(user_id, jti)):
            # Token desconhecido/revogado — possível reuso. Falha fechada.
            raise AuthenticationError("Refresh token revogado.")

        user = await self.users.get(payload["sub"])
        if user is None or not user.is_active:
            raise AuthenticationError("Usuário inválido.")

        # Rotação: invalida o refresh atual e emite um novo par.
        await self.redis.delete(_refresh_key(user_id, jti))
        return await self._issue_token_pair(user)

    async def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, TokenType.REFRESH)
        except JWTError:
            return  # logout é idempotente
        await self.redis.delete(_refresh_key(payload["sub"], payload["jti"]))

    async def _issue_token_pair(self, user: User) -> TokenPair:
        access, _ = create_access_token(str(user.id), {"role": user.role.value})
        refresh, jti = create_refresh_token(str(user.id))
        await self.redis.set(
            _refresh_key(str(user.id), jti),
            "1",
            ex=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
        return TokenPair(access_token=access, refresh_token=refresh)
