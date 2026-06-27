# Design — Tracing OpenTelemetry (Fase 4, iteração 4)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

Completa o tripé de observabilidade (métricas ✅, logs estruturados ✅, **traces**).
Esta iteração instrumenta a API com **OpenTelemetry** — spans de **FastAPI**,
**SQLAlchemy** e **Redis** — exportando via **OTLP/HTTP** para um **Jaeger**
(coletor no profile `observability`).

Tracing é **opt-in** (`TRACING_ENABLED`, default `false`): runs e testes normais
não exportam nada. Sem migration. Branch parte de `main`.

## Decisões fechadas

- **SDK + auto-instrumentação programática** (não o wrapper `opentelemetry-instrument`),
  para controle no `create_app`.
- **Exporter OTLP/HTTP** (`opentelemetry-exporter-otlp-proto-http`, porta 4318) —
  evita `grpcio` (build pesado). Endpoint configurável.
- **Coletor:** Jaeger all-in-one no profile `observability` (UI 16686, OTLP HTTP
  4318).
- **Escopo:** API (FastAPI + SQLAlchemy + Redis). O **worker ARQ** fica de fora
  (sem instrumentação oficial; roda `arq ...`, não `create_app`).
- **Toggle:** `TRACING_ENABLED: bool = False`. Quando `false`, `create_app` não
  chama o setup — comportamento atual inalterado (testes não quebram).
- **service.name** = `PROJECT_NAME`.

## Componentes

### Dependências (`pyproject.toml`, runtime)
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-http`
- `opentelemetry-instrumentation-fastapi`
- `opentelemetry-instrumentation-sqlalchemy`
- `opentelemetry-instrumentation-redis`

### Config (`app/core/config.py` + `.env.example`)
- `TRACING_ENABLED: bool = False`
- `OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://jaeger:4318/v1/traces"`

### `app/core/tracing.py`
```python
_provider_configured = False

def setup_tracing(app: FastAPI, *, span_exporter: SpanExporter | None = None) -> None:
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
- guarda `_provider_configured`: provider + instrumentação global (DB/Redis) uma
  vez por processo; `instrument_app` por instância de app (idempotência em testes).
- `span_exporter` injetável → testes usam `InMemorySpanExporter`.

### `app/main.py`
- em `create_app`, após `setup_metrics`:
```python
    if settings.TRACING_ENABLED:
        setup_tracing(app)
```

### Docker (`docker/docker-compose.yml`)
```yaml
  jaeger:
    image: jaegertracing/all-in-one:latest
    profiles: ["observability"]
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    ports:
      - "16686:16686"   # UI
      - "4318:4318"     # OTLP HTTP
    restart: unless-stopped
```
> Para ver traces: `TRACING_ENABLED=true` no `.env` + subir com
> `--profile observability` (traz o Jaeger). Com tracing on e sem coletor, o
> BatchSpanProcessor apenas loga falha de export; a app segue normal.

## Arquivos

**Novos:** `app/core/tracing.py`, `tests/unit/test_tracing.py`.

**Editados:** `pyproject.toml`, `app/core/config.py`, `.env.example`,
`app/main.py`, `docker/docker-compose.yml`, `README.md`.

## Testes

**Unit** (`test_tracing.py`, sem coletor/DB):
- `TRACING_ENABLED` default `False` (garante que o comportamento padrão não muda).
- `setup_tracing` num app FastAPI mínimo com `InMemorySpanExporter`: após um
  request a um endpoint, `force_flush` e assert de **≥1 span** com o nome/rota —
  prova que a instrumentação FastAPI gera spans. **Validado localmente.**

> SQLAlchemy/Redis instrumentam o engine/cliente **globais** (não os de teste),
> então spans de DB não aparecem para requests de teste — o teste foca no span
> HTTP (FastAPI), que é o que dá para asserir de forma confiável sem coletor.

**Integration:** nenhuma nova (tracing off por default; coletor é externo). A
validação fim-a-fim é manual no Docker (Jaeger UI).

**Gates:** ruff + ruff format + mypy strict + pytest verdes.

## Verificação

- `ruff`/`mypy`/`pytest` verdes; **prova local** do span via `InMemorySpanExporter`.
- Docker: `.env` com `TRACING_ENABLED=true`; `docker compose --profile
  observability up --build`; gerar tráfego; **Jaeger UI** (<http://localhost:16686>)
  mostra o serviço `StockGuardian` e traces com spans de FastAPI/SQLAlchemy/Redis.

## Fora de escopo (futuro)

- Tracing do worker ARQ e correlação com `correlation_id` dos logs.
- Propagação de contexto entre serviços externos.
- Sampling avançado / tail-based.
- Alertmanager e deploy/manifests (próximas fatias).
