"""Rotas de autenticação. Rotas finas: delegam toda a lógica ao AuthService."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.permissions import permissions_for
from app.dependencies.auth import CurrentUser
from app.dependencies.db import DBSession, RedisClient
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.schemas.user import UserMe, UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, session: DBSession, redis: RedisClient) -> UserRead:
    user = await AuthService(session, redis).register(data)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(data: LoginRequest, session: DBSession, redis: RedisClient) -> TokenPair:
    return await AuthService(session, redis).login(data.email, data.password)


@router.post("/login/form", response_model=TokenPair, include_in_schema=False)
async def login_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: DBSession,
    redis: RedisClient,
) -> TokenPair:
    """Login compatível com OAuth2 (usado pelo botão Authorize do Swagger)."""
    return await AuthService(session, redis).login(form.username, form.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshRequest, session: DBSession, redis: RedisClient) -> TokenPair:
    return await AuthService(session, redis).refresh(data.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshRequest, session: DBSession, redis: RedisClient) -> None:
    await AuthService(session, redis).logout(data.refresh_token)


@router.get("/me", response_model=UserMe)
async def me(current_user: CurrentUser) -> UserMe:
    perms = sorted(p.value for p in permissions_for(current_user.role))
    data = UserRead.model_validate(current_user).model_dump()
    return UserMe(**data, permissions=perms)
