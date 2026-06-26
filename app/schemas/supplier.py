from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_DOCUMENT_RE = re.compile(r"\D")


class SupplierBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    document: str = Field(min_length=11, max_length=18, description="CPF/CNPJ (só dígitos).")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool = True

    @field_validator("document")
    @classmethod
    def normalize_document(cls, v: str) -> str:
        """Remove máscara, mantém apenas dígitos."""
        digits = _DOCUMENT_RE.sub("", v)
        if len(digits) not in (11, 14):
            raise ValueError("Documento deve ter 11 (CPF) ou 14 (CNPJ) dígitos.")
        return digits


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class SupplierRead(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
