"""Serviço de produtos."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.domain import ConflictError, NotFoundError
from app.models.product import Product
from app.repositories.product import ProductRepository
from app.repositories.supplier import SupplierRepository
from app.schemas.common import Page, PaginationParams
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.alert import AlertService


class ProductService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ProductRepository(session)
        self.suppliers = SupplierRepository(session)

    async def get(self, product_id: uuid.UUID) -> Product:
        product = await self.repo.get(product_id)
        if product is None:
            raise NotFoundError("Produto", product_id)
        return product

    async def list(self, params: PaginationParams) -> Page[Product]:
        items = await self.repo.list(offset=params.offset, limit=params.limit)
        total = await self.repo.count()
        return Page.create(items, total, params)

    async def create(self, data: ProductCreate) -> Product:
        if await self.repo.get_by_sku(data.sku):
            raise ConflictError("SKU já cadastrado.", details={"field": "sku"})
        if await self.suppliers.get(data.supplier_id) is None:
            raise NotFoundError("Fornecedor", data.supplier_id)
        product = Product(**data.model_dump())
        await self.repo.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def update(self, product_id: uuid.UUID, data: ProductUpdate) -> Product:
        product = await self.get(product_id)
        payload = data.model_dump(exclude_unset=True)
        if "supplier_id" in payload and await self.suppliers.get(payload["supplier_id"]) is None:
            raise NotFoundError("Fornecedor", payload["supplier_id"])
        for field, value in payload.items():
            setattr(product, field, value)
        # Alterar mínimo/quantidade pode abrir ou resolver alerta sem movimentação.
        if "min_stock" in payload or "quantity" in payload:
            await self.session.flush()
            await AlertService(self.session).evaluate(product)
        await self.session.commit()
        await self.session.refresh(product)
        return product

    async def delete(self, product_id: uuid.UUID) -> None:
        product = await self.get(product_id)
        await self.repo.delete(product)
        await self.session.commit()
