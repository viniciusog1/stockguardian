"""Métricas Prometheus: Counters de negócio + setup do instrumentator HTTP."""

from __future__ import annotations

import contextlib

from fastapi import FastAPI
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

MOVEMENTS_TOTAL = Counter(
    "stockguardian_movements_total",
    "Total de movimentações de estoque registradas.",
    ["type"],
)
ALERTS_OPENED_TOTAL = Counter(
    "stockguardian_alerts_opened_total",
    "Total de alertas abertos.",
    ["kind"],
)
ALERTS_RESOLVED_TOTAL = Counter(
    "stockguardian_alerts_resolved_total",
    "Total de alertas resolvidos.",
    ["kind"],
)
REPORT_JOBS_ENQUEUED_TOTAL = Counter(
    "stockguardian_report_jobs_enqueued_total",
    "Total de jobs de relatório enfileirados.",
    ["report"],
)


def setup_metrics(app: FastAPI) -> None:
    """Instrumenta a app (HTTP) e expõe /metrics.

    Idempotente entre instâncias de app no mesmo processo (ex.: múltiplos
    ``create_app`` nos testes) — se as séries HTTP já estiverem registradas no
    registry global, reaproveita sem falhar.
    """
    instrumentator = Instrumentator()
    # ValueError: métricas HTTP já registradas no processo (múltiplos create_app);
    # segue só com a exposição.
    with contextlib.suppress(ValueError):
        instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
