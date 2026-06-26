"""Serviço de fornecedores."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.domain import ConflictError, NotFoundError
from app.models.supplier import Supplier
from app.repositories.supplier import SupplierRepository
from app.schemas.common import Page, PaginationParams
from app.schemas.supplier import SupplierCreate, SupplierUpdate


class SupplierService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SupplierRepository(session)

    async def get(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self.repo.get(supplier_id)
        if supplier is None:
            raise NotFoundError("Fornecedor", supplier_id)
        return supplier

    async def list(self, params: PaginationParams) -> Page[Supplier]:
        items = await self.repo.list(offset=params.offset, limit=params.limit)
        total = await self.repo.count()
        return Page.create(items, total, params)

    async def create(self, data: SupplierCreate) -> Supplier:
        if await self.repo.get_by_document(data.document):
            raise ConflictError("Documento já cadastrado.", details={"field": "document"})
        supplier = Supplier(**data.model_dump())
        await self.repo.add(supplier)
        await self.session.commit()
        await self.session.refresh(supplier)
        return supplier

    async def update(self, supplier_id: uuid.UUID, data: SupplierUpdate) -> Supplier:
        supplier = await self.get(supplier_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(supplier, field, value)
        await self.session.commit()
        await self.session.refresh(supplier)
        return supplier

    async def delete(self, supplier_id: uuid.UUID) -> None:
        supplier = await self.get(supplier_id)
        await self.repo.delete(supplier)
        await self.session.commit()
