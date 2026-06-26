"""Rotas administrativas de usuários — restritas a ADMIN."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import require_role
from app.dependencies.db import DBSession
from app.models.user import UserRole
from app.schemas.common import Page
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.user import UserService
from app.utils.pagination import Pagination

# Todas as rotas exigem papel ADMIN.
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.get("", response_model=Page[UserRead])
async def list_users(session: DBSession, pagination: Pagination) -> Page[UserRead]:
    page = await UserService(session).list(pagination)
    return Page[UserRead].create(
        [UserRead.model_validate(u) for u in page.items], page.total, pagination
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, session: DBSession) -> UserRead:
    user = await UserService(session).create(data)
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: uuid.UUID, session: DBSession) -> UserRead:
    user = await UserService(session).get(user_id)
    return UserRead.model_validate(user)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(user_id: uuid.UUID, data: UserUpdate, session: DBSession) -> UserRead:
    user = await UserService(session).update(user_id, data)
    return UserRead.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: uuid.UUID, session: DBSession) -> None:
    await UserService(session).delete(user_id)
