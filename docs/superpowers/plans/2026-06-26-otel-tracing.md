# Tracing OpenTelemetry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrumentar a API com OpenTelemetry (FastAPI + SQLAlchemy + Redis),
exportando via OTLP/HTTP para Jaeger (profile `observability`). Opt-in por
`TRACING_ENABLED` (default off). Sem migration.

**Architecture:** `app/core/tracing.py::setup_tracing(app)` configura provider +
instrumentações; `create_app` chama quando `TRACING_ENABLED`. Jaeger no compose.

**Tech Stack:** OpenTelemetry SDK + OTLP HTTP exporter + instrumentations FastAPI/
SQLAlchemy/Redis; Jaeger.

Spec: `docs/superpowers/specs/2026-06-26-otel-tracing-design.md`.

---

## Convenção de testes (ambiente)

Unit roda local (com `InMemorySpanExporter`, sem coletor). Validação fim-a-fim no
Jaeger é manual no Docker.

---

## Task 1: Dependências + config

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Deps (runtime)**

`pyproject.toml`, `[project].dependencies`:
```toml
    "opentelemetry-sdk>=1.27.0",
    "opentelemetry-exporter-otlp-proto-http>=1.27.0",
    "opentelemetry-instrumentation-fastapi>=0.48b0",
    "opentelemetry-instrumentation-sqlalchemy>=0.48b0",
    "opentelemetry-instrumentation-redis>=0.48b0",
```

- [ ] **Step 2: Config**

`app/core/config.py` (seção Aplicação):
```python
    TRACING_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://jaeger:4318/v1/traces"
```
`.env.example` (nova seção / junto da Observabilidade):
```
TRACING_ENABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318/v1/traces
```

- [ ] **Step 3: Instalar + import**

TESTRUN `python -c "from opentelemetry.sdk.trace import TracerProvider; from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor; print('ok')"`

- [ ] **Step 4: Commit**
```bash
git add pyproject.toml app/core/config.py .env.example
git commit -m "build(tracing): deps OpenTelemetry + TRACING_ENABLED/OTLP endpoint"
```

---

## Task 2: setup_tracing + wiring + unit (validado local)

**Files:**
- Create: `app/core/tracing.py`
- Modify: `app/main.py`
- Create: `tests/unit/test_tracing.py`

- [ ] **Step 1: tracing.py**

`app/core/tracing.py`:
```python
"""Tracing OpenTelemetry: provider + instrumentação (FastAPI/SQLAlchemy/Redis)."""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from app.core.config import settings
from app.core.database import engine

_provider_configured = False


def setup_tracing(app: FastAPI, *, span_exporter: SpanExporter | None = None) -> None:
    """Configura o tracing e instrumenta a app. Idempotente entre instâncias."""
    global _provider_configured
    if not _provider_configured:
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.PROJECT_NAME})
        )
        exporter = span_exporter or OTLPSpanExporter(
            endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        RedisInstrumentor().instrument()
        _provider_configured = True
    FastAPIInstrumentor.instrument_app(app)
```

- [ ] **Step 2: Wiring no main**

`app/main.py`:
- import: `from app.core.tracing import setup_tracing`.
- em `create_app`, após o bloco de métricas:
```python
    if settings.TRACING_ENABLED:
        setup_tracing(app)
```

- [ ] **Step 3: Unit**

`tests/unit/test_tracing.py`:
```python
"""Unit: setup_tracing gera spans (InMemorySpanExporter) e default off."""

from __future__ import annotations

import anyio
import httpx
import pytest
from app.core.config import settings
from app.core.tracing import setup_tracing
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
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

    # injeta o exporter de memória (SimpleSpanProcessor flush imediato)
    setup_tracing(app, span_exporter=exporter)

    async def go() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            await c.get("/ping")

    anyio.run(go)
    trace_provider = __import__("opentelemetry").trace.get_tracer_provider()
    trace_provider.force_flush()  # type: ignore[attr-defined]
    spans = exporter.get_finished_spans()
    assert any("/ping" in (s.name or "") for s in spans)
```
> Nota de implementação: se o `BatchSpanProcessor` não entregar a tempo no teste,
> trocar para `SimpleSpanProcessor` quando `span_exporter` for injetado (decidir
> no Step 4 com o teste real). Mantido `SimpleSpanProcessor` no import para esse
> ajuste.

- [ ] **Step 4: Rodar unit + ajustar até passar (validação local real)**

TESTRUN `pytest tests/unit/test_tracing.py -q`
Expected: PASS. Se o span HTTP não aparecer, ajustar `setup_tracing` para usar
`SimpleSpanProcessor` quando `span_exporter` é injetado, e re-rodar.

- [ ] **Step 5: ruff + mypy + boot**

TESTRUN `ruff check app/core/tracing.py tests/unit/test_tracing.py && mypy app`
TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`

- [ ] **Step 6: Commit**
```bash
git add app/core/tracing.py app/main.py tests/unit/test_tracing.py
git commit -m "feat(tracing): setup OpenTelemetry (FastAPI/SQLAlchemy/Redis) + unit"
```

---

## Task 3: Jaeger no compose + README + gates

**Files:**
- Modify: `docker/docker-compose.yml`
- Modify: `README.md`

- [ ] **Step 1: Serviço jaeger (profile observability)**

Em `docker/docker-compose.yml`, junto dos serviços de observabilidade:
```yaml
  jaeger:
    image: jaegertracing/all-in-one:latest
    profiles: ["observability"]
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    ports:
      - "16686:16686"
      - "4318:4318"
    restart: unless-stopped
```

- [ ] **Step 2: README**

- na subseção de Observabilidade, acrescentar:
```markdown
- Jaeger (tracing): <http://localhost:16686> — defina `TRACING_ENABLED=true` no `.env`
  e suba com `--profile observability`; o serviço `StockGuardian` aparece com traces
  de FastAPI/SQLAlchemy/Redis.
```
- Stack: adicionar "Tracing | OpenTelemetry (OTLP → Jaeger)".
- roadmap:
```markdown
- [ ] **Fase 4**: ~~métricas~~ ✅ · ~~health/readiness~~ ✅ · ~~scrape~~ ✅ · ~~tracing OTel~~ ✅ · deploy/monitoramento
```

- [ ] **Step 3: Validar YAML + gates**

TESTRUN `python -c "import yaml; d=yaml.safe_load(open('docker/docker-compose.yml', encoding='utf-8')); print(sorted(d['services']))"`
Expected: inclui `jaeger`.
TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: tudo verde.

- [ ] **Step 4: Validar no Docker (dev)**

```bash
# .env: TRACING_ENABLED=true
docker compose -f docker/docker-compose.yml --profile observability up -d --build
# gerar tráfego (login, listar produtos, movimentar) e abrir o Jaeger:
#   http://localhost:16686  -> Service: StockGuardian -> Find Traces
```

- [ ] **Step 5: Commit + push**
```bash
git add docker/docker-compose.yml README.md
git commit -m "docs(tracing): Jaeger no compose + Fase 4 atualizada"
git push -u origin feat/otel-tracing
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** deps+config (T1), setup_tracing + wiring + unit do span
  (T2), Jaeger no compose + README + gates (T3). ✔
- **Placeholders:** nenhum.
- **Consistência:** `setup_tracing` chamado em `create_app` sob `TRACING_ENABLED`;
  endpoint OTLP == porta 4318 do Jaeger; `service.name` = `PROJECT_NAME`; exporter
  injetável usado no unit.
- **Sem migration / sem nova permissão. Tracing off por default** → suíte e runs
  normais inalterados.
- **Risco endereçado:** entrega de span no teste — validar com exporter de memória
  e, se preciso, `SimpleSpanProcessor` para flush síncrono (decidido no T2-step4).
