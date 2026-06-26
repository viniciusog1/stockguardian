from __future__ import annotations

from app.models.supplier import Supplier
from app.repositories.base import BaseRepository


class SupplierRepository(BaseRepository[Supplier]):
    model = Supplier

    async def get_by_document(self, document: str) -> Supplier | None:
        return await self.get_by(document=document)
