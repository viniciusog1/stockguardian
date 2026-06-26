"""Rotas CRUD de produtos."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import CurrentUser, require_role
from app.dependencies.db import DBSession
from app.models.user import UserRole
from app.schemas.common import Page
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate
from app.services.product import ProductService
from app.utils.pagination import Pagination

router = APIRouter(prefix="/products", tags=["products"])

ManagerUp = Depends(require_role(UserRole.MANAGER))


@router.get("", response_model=Page[ProductRead])
async def list_products(
    session: DBSession, _: CurrentUser, pagination: Pagination
) -> Page[ProductRead]:
    page = await ProductService(session).list(pagination)
    return Page[ProductRead].create(
        [ProductRead.model_validate(p) for p in page.items], page.total, pagination
    )


@router.get("/{product_id}", response_model=ProductRead)
async def get_product(product_id: uuid.UUID, session: DBSession, _: CurrentUser) -> ProductRead:
    product = await ProductService(session).get(product_id)
    return ProductRead.model_validate(product)


@router.post(
    "", response_model=ProductRead, status_code=status.HTTP_201_CREATED, dependencies=[ManagerUp]
)
async def create_product(data: ProductCreate, session: DBSession) -> ProductRead:
    product = await ProductService(session).create(data)
    return ProductRead.model_validate(product)


@router.patch("/{product_id}", response_model=ProductRead, dependencies=[ManagerUp])
async def update_product(
    product_id: uuid.UUID, data: ProductUpdate, session: DBSession
) -> ProductRead:
    product = await ProductService(session).update(product_id, data)
    return ProductRead.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[ManagerUp])
async def delete_product(product_id: uuid.UUID, session: DBSession) -> None:
    await ProductService(session).delete(product_id)
