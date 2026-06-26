"""Rotas de relatórios operacionais (read-only, MANAGER+).

Inclui exports síncronos (`.xlsx` na request) e o ciclo assíncrono via ARQ
(enfileira → consulta status → baixa o resultado).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi import status as http_status

from app.core.permissions import Permission
from app.dependencies.auth import require_permission
from app.dependencies.db import DBSession
from app.dependencies.queue import ReportQueue
from app.exceptions.domain import ConflictError, NotFoundError
from app.schemas.report import InventoryValuationReport, MovementsSummaryReport
from app.schemas.report_job import ReportJobAccepted, ReportJobState, ReportJobStatus
from app.services.report import ReportService
from app.utils.excel import (
    ExportFile,
    inventory_valuation_export_file,
    movements_summary_export_file,
)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_permission(Permission.REPORT_READ))],
)


def _xlsx_response(export: ExportFile) -> Response:
    return Response(
        content=export.content,
        media_type=export.media_type,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
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
    return _xlsx_response(inventory_valuation_export_file(report))


@router.post(
    "/inventory-valuation/export-async",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=ReportJobAccepted,
)
async def inventory_valuation_export_async(
    queue: ReportQueue,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    only_active: Annotated[bool, Query()] = True,
) -> ReportJobAccepted:
    job_id = await queue.enqueue_inventory_valuation(
        supplier_id=supplier_id, only_active=only_active
    )
    return ReportJobAccepted(job_id=job_id, status=ReportJobState.QUEUED)


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
    return _xlsx_response(movements_summary_export_file(report))


@router.post(
    "/movements-summary/export-async",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=ReportJobAccepted,
)
async def movements_summary_export_async(
    queue: ReportQueue,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> ReportJobAccepted:
    job_id = await queue.enqueue_movements_summary(
        product_id=product_id, date_from=date_from, date_to=date_to
    )
    return ReportJobAccepted(job_id=job_id, status=ReportJobState.QUEUED)


@router.get("/jobs/{job_id}", response_model=ReportJobStatus)
async def report_job_status(job_id: str, queue: ReportQueue) -> ReportJobStatus:
    state = await queue.get_status(job_id)
    if state is ReportJobState.NOT_FOUND:
        raise NotFoundError("Job de relatório", job_id)
    return ReportJobStatus(job_id=job_id, status=state)


@router.get("/jobs/{job_id}/download")
async def report_job_download(job_id: str, queue: ReportQueue) -> Response:
    state = await queue.get_status(job_id)
    if state is ReportJobState.NOT_FOUND:
        raise NotFoundError("Job de relatório", job_id)
    if state is ReportJobState.FAILED:
        raise ConflictError("A geração do relatório falhou.", details={"status": state.value})
    if state is not ReportJobState.COMPLETE:
        raise ConflictError("Relatório ainda em processamento.", details={"status": state.value})
    export = await queue.get_result(job_id)
    if export is None:
        raise NotFoundError("Resultado do relatório", job_id)
    return _xlsx_response(export)
