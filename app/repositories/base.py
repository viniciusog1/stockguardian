"""Repository Pattern — encapsula o acesso ao banco.

Serviços dependem desta abstração e nunca emitem SQL diretamente, o que mantém a
regra de negócio testável (repos podem ser mockados) e o acesso a dados isolado.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """CRUD genérico assíncrono para um modelo.

    Os métodos fazem ``flush`` (não ``commit``) — o controle de transação fica
    no serviço, permitindo agrupar várias operações atomicamente.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def get_by(self, **filters: Any) -> ModelT | None:
        stmt = select(self.model).filter_by(**filters).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        order_by: Any | None = None,
        **filters: Any,
    ) -> list[ModelT]:
        stmt = select(self.model).filter_by(**filters)
        # Todos os modelos têm `id` (via UUIDMixin); o bound genérico não expõe isso.
        default_order = self.model.id  # type: ignore[attr-defined]
        stmt = stmt.order_by(order_by if order_by is not None else default_order)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()
