"""Tracing OpenTelemetry: provider + instrumentação (FastAPI/SQLAlchemy/Redis)."""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)

from app.core.config import settings
from app.core.database import engine

_provider_configured = False


def setup_tracing(app: FastAPI, *, span_exporter: SpanExporter | None = None) -> None:
    """Configura o tracing e instrumenta a app. Idempotente entre instâncias.

    O provider e a instrumentação global (DB/Redis) são feitos uma vez por
    processo; ``instrument_app`` roda por instância de app. Um ``span_exporter``
    injetado (testes) usa processamento síncrono para flush imediato.
    """
    global _provider_configured
    if not _provider_configured:
        provider = TracerProvider(resource=Resource.create({"service.name": settings.PROJECT_NAME}))
        processor: SpanProcessor
        if span_exporter is not None:
            processor = SimpleSpanProcessor(span_exporter)
        else:
            processor = BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
            )
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        RedisInstrumentor().instrument()
        _provider_configured = True
    FastAPIInstrumentor.instrument_app(app)
