"""Abstração da fila de jobs de relatório sobre o ARQ.

Encapsula enqueue/status/result para que rotas (e testes) não dependam do ARQ
diretamente. ``map_job_status`` é pura e testável.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus

from app.exceptions.domain import ConflictError
from app.schemas.report_job import ReportJobState
from app.utils.excel import ExportFile


def map_job_status(status: JobStatus, *, success: bool | None = None) -> ReportJobState:
    """Mapeia o JobStatus do ARQ para o estado exposto na API.

    ``success`` só é relevante quando o status é ``complete``.
    """
    if status in (JobStatus.deferred, JobStatus.queued):
        return ReportJobState.QUEUED
    if status == JobStatus.in_progress:
        return ReportJobState.IN_PROGRESS
    if status == JobStatus.not_found:
        return ReportJobState.NOT_FOUND
    return ReportJobState.COMPLETE if success else ReportJobState.FAILED


def _require_job_id(job: Job | None) -> str:
    if job is None:
        raise ConflictError("Não foi possível enfileirar o relatório.")
    return job.job_id


class ReportJobQueue:
    def __init__(self, pool: ArqRedis) -> None:
        self.pool = pool

    async def enqueue_inventory_valuation(
        self, *, supplier_id: uuid.UUID | None, only_active: bool
    ) -> str:
        job = await self.pool.enqueue_job(
            "generate_inventory_valuation_export",
            supplier_id=supplier_id,
            only_active=only_active,
        )
        return _require_job_id(job)

    async def enqueue_movements_summary(
        self,
        *,
        product_id: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> str:
        job = await self.pool.enqueue_job(
            "generate_movements_summary_export",
            product_id=product_id,
            date_from=date_from,
            date_to=date_to,
        )
        return _require_job_id(job)

    async def get_status(self, job_id: str) -> ReportJobState:
        job = Job(job_id, self.pool)
        status = await job.status()
        if status != JobStatus.complete:
            return map_job_status(status)
        info = await job.result_info()
        return map_job_status(status, success=bool(info and info.success))

    async def get_result(self, job_id: str) -> ExportFile | None:
        job = Job(job_id, self.pool)
        if await job.status() != JobStatus.complete:
            return None
        info = await job.result_info()
        if info is None or not info.success:
            return None
        data = info.result
        return ExportFile(
            filename=data["filename"],
            media_type=data["media_type"],
            content=data["content"],
        )
