"""Rotas CRUD de fornecedores."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import CurrentUser, require_role
from app.dependencies.db import DBSession
from app.models.user import UserRole
from app.schemas.common import Page
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services.supplier import SupplierService
from app.utils.pagination import Pagination

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

# Escrita exige MANAGER+ ; leitura, qualquer usuário autenticado.
ManagerUp = Depends(require_role(UserRole.MANAGER))


@router.get("", response_model=Page[SupplierRead])
async def list_suppliers(
    session: DBSession, _: CurrentUser, pagination: Pagination
) -> Page[SupplierRead]:
    page = await SupplierService(session).list(pagination)
    return Page[SupplierRead].create(
        [SupplierRead.model_validate(s) for s in page.items], page.total, pagination
    )


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier(supplier_id: uuid.UUID, session: DBSession, _: CurrentUser) -> SupplierRead:
    supplier = await SupplierService(session).get(supplier_id)
    return SupplierRead.model_validate(supplier)


@router.post(
    "", response_model=SupplierRead, status_code=status.HTTP_201_CREATED, dependencies=[ManagerUp]
)
async def create_supplier(data: SupplierCreate, session: DBSession) -> SupplierRead:
    supplier = await SupplierService(session).create(data)
    return SupplierRead.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierRead, dependencies=[ManagerUp])
async def update_supplier(
    supplier_id: uuid.UUID, data: SupplierUpdate, session: DBSession
) -> SupplierRead:
    supplier = await SupplierService(session).update(supplier_id, data)
    return SupplierRead.model_validate(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[ManagerUp])
async def delete_supplier(supplier_id: uuid.UUID, session: DBSession) -> None:
    await SupplierService(session).delete(supplier_id)
