"""Tasks ARQ: geração assíncrona dos exports de relatório.

A session factory vem do ctx (injetada no on_startup do worker), mantendo as
tasks desacopladas do engine global e testáveis com a sessão de teste.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.services.report import ReportService
from app.utils.excel import (
    ExportFile,
    inventory_valuation_export_file,
    movements_summary_export_file,
)


def _serialize(export: ExportFile) -> dict[str, Any]:
    return {
        "filename": export.filename,
        "media_type": export.media_type,
        "content": export.content,
    }


async def generate_inventory_valuation_export(
    ctx: dict[str, Any],
    *,
    supplier_id: uuid.UUID | None = None,
    only_active: bool = True,
) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        report = await ReportService(session).inventory_valuation(
            supplier_id=supplier_id, only_active=only_active
        )
    return _serialize(inventory_valuation_export_file(report))


async def generate_movements_summary_export(
    ctx: dict[str, Any],
    *,
    product_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        report = await ReportService(session).movements_summary(
            product_id=product_id, date_from=date_from, date_to=date_to
        )
    return _serialize(movements_summary_export_file(report))
