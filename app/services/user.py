"""Serviço de gestão de usuários (operações administrativas)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.exceptions.domain import ConflictError, NotFoundError
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.common import Page, PaginationParams
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def get(self, user_id: uuid.UUID) -> User:
        user = await self.repo.get(user_id)
        if user is None:
            raise NotFoundError("Usuário", user_id)
        return user

    async def list(self, params: PaginationParams) -> Page[User]:
        items = await self.repo.list(offset=params.offset, limit=params.limit)
        total = await self.repo.count()
        return Page.create(items, total, params)

    async def create(self, data: UserCreate) -> User:
        if await self.repo.get_by_email(data.email):
            raise ConflictError("E-mail já cadastrado.", details={"field": "email"})
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=data.role,
            is_active=data.is_active,
        )
        await self.repo.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get(user_id)
        payload = data.model_dump(exclude_unset=True)
        if "password" in payload:
            user.hashed_password = hash_password(payload.pop("password"))
        for field, value in payload.items():
            setattr(user, field, value)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete(self, user_id: uuid.UUID) -> None:
        user = await self.get(user_id)
        await self.repo.delete(user)
        await self.session.commit()
