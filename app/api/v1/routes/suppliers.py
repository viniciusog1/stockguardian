"""Rotas CRUD de fornecedores."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.core.permissions import Permission
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.db import DBSession
from app.schemas.common import Page
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services.supplier import SupplierService
from app.utils.pagination import Pagination

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

# Escrita exige supplier:write; leitura, qualquer usuário autenticado.
CanWrite = Depends(require_permission(Permission.SUPPLIER_WRITE))


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
    "", response_model=SupplierRead, status_code=status.HTTP_201_CREATED, dependencies=[CanWrite]
)
async def create_supplier(data: SupplierCreate, session: DBSession) -> SupplierRead:
    supplier = await SupplierService(session).create(data)
    return SupplierRead.model_validate(supplier)


@router.patch("/{supplier_id}", response_model=SupplierRead, dependencies=[CanWrite])
async def update_supplier(
    supplier_id: uuid.UUID, data: SupplierUpdate, session: DBSession
) -> SupplierRead:
    supplier = await SupplierService(session).update(supplier_id, data)
    return SupplierRead.model_validate(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[CanWrite])
async def delete_supplier(supplier_id: uuid.UUID, session: DBSession) -> None:
    await SupplierService(session).delete(supplier_id)
