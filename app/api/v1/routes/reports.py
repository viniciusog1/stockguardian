"""Rotas de relatórios operacionais (read-only, MANAGER+)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.permissions import Permission
from app.dependencies.auth import require_permission
from app.dependencies.db import DBSession
from app.schemas.report import InventoryValuationReport, MovementsSummaryReport
from app.services.report import ReportService
from app.utils.excel import (
    XLSX_MEDIA_TYPE,
    inventory_valuation_workbook,
    movements_summary_workbook,
    workbook_to_bytes,
)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_permission(Permission.REPORT_READ))],
)


@router.get("/inventory-valuation", response_model=InventoryValuationReport)
async def inventory_valuation(
    session: DBSession,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    only_active: Annotated[bool, Query()] = True,
) -> InventoryValuationReport:
    return await ReportService(session).inventory_valuation(
        supplier_id=supplier_id, only_active=only_active
    )


@router.get("/inventory-valuation/export")
async def inventory_valuation_export(
    session: DBSession,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    only_active: Annotated[bool, Query()] = True,
) -> Response:
    report = await ReportService(session).inventory_valuation(
        supplier_id=supplier_id, only_active=only_active
    )
    content = workbook_to_bytes(inventory_valuation_workbook(report))
    filename = f"inventory-valuation-{report.generated_at.date().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/movements-summary", response_model=MovementsSummaryReport)
async def movements_summary(
    session: DBSession,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> MovementsSummaryReport:
    return await ReportService(session).movements_summary(
        product_id=product_id, date_from=date_from, date_to=date_to
    )


@router.get("/movements-summary/export")
async def movements_summary_export(
    session: DBSession,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> Response:
    report = await ReportService(session).movements_summary(
        product_id=product_id, date_from=date_from, date_to=date_to
    )
    content = workbook_to_bytes(movements_summary_workbook(report))
    filename = f"movements-summary-{report.generated_at.date().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
