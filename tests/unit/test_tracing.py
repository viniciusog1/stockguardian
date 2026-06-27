"""Unit: setup_tracing gera spans (InMemorySpanExporter) e default off."""

from __future__ import annotations

import anyio
import httpx
import pytest
from app.core.config import settings
from app.core.tracing import setup_tracing
from fastapi import FastAPI
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

pytestmark = pytest.mark.unit


def test_tracing_disabled_by_default() -> None:
    assert settings.TRACING_ENABLED is False


def test_setup_tracing_produces_http_span() -> None:
    exporter = InMemorySpanExporter()

    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    setup_tracing(app, span_exporter=exporter)

    async def go() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.get("/ping")
            assert resp.status_code == 200

    anyio.run(go)

    spans = exporter.get_finished_spans()
    assert any("/ping" in (s.name or "") for s in spans), [s.name for s in spans]
