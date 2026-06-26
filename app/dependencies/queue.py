"""Dependência da fila de jobs de relatório (ARQ)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.queue import get_arq_pool
from app.services.report_jobs import ReportJobQueue


async def get_report_queue() -> ReportJobQueue:
    return ReportJobQueue(await get_arq_pool())


ReportQueue = Annotated[ReportJobQueue, Depends(get_report_queue)]
