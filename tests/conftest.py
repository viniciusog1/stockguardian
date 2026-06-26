"""Fixtures de teste.

Integração roda contra um Postgres real (tipos UUID/ENUM e ``FOR UPDATE`` exigem
o dialeto Postgres). O Redis é substituído por ``fakeredis`` — sem I/O externo.

Cada teste cria seu próprio engine com ``NullPool`` e recria o schema. Isso evita
o problema clássico do pytest-asyncio: um engine async de escopo de sessão
reutiliza conexões presas a um event loop que já foi fechado por outro teste.

Defina ``TEST_DATABASE_URL`` para apontar a um banco de testes; o default usa
``stockguardian_test`` em localhost.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from app.core.security import hash_password
from app.dependencies.auth import get_current_active_user
from app.dependencies.db import get_db, get_redis_client
from app.main import create_app
from app.models import Base, User, UserRole
from fakeredis import aioredis as fake_aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://stockguardian:stockguardian@localhost:5432/stockguardian_test",
)


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    """Engine isolado por teste (NullPool) + schema recriado do zero."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[fake_aioredis.FakeRedis]:
    client = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture
async def client(
    db_engine: AsyncEngine, redis_client: fake_aioredis.FakeRedis
) -> AsyncGenerator[AsyncClient]:
    """Cliente HTTP com DB/Redis de teste injetados via dependency_overrides.

    Cada request recebe sua própria sessão (igual a produção).
    """
    app = create_app()
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis_client] = lambda: redis_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac._app = app  # type: ignore[attr-defined]  # acesso ao app p/ overrides nos testes
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email="admin@test.com",
        hashed_password=hash_password("Admin@123"),
        full_name="Admin Teste",
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, admin_user: User) -> AsyncClient:
    """Cliente autenticado como admin — força o usuário atual via override."""
    app = client._app  # type: ignore[attr-defined]
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    return client
