"""Camada de acesso ao banco (SQLAlchemy 2.x async).

Expõe o engine async, a factory de sessões e a `Base` declarativa. A obtenção de
sessão por request fica em `app.dependencies.db`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,  # descarta conexões mortas antes de usar
    future=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # objetos seguem utilizáveis após commit
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Cede uma sessão e garante fechamento. Use via Depends nas rotas."""
    async with async_session_factory() as session:
        yield session
