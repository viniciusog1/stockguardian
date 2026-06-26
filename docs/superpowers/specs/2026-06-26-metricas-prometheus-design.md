# Design — Métricas Prometheus (Fase 4, iteração 1)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

Inicia a **Fase 4 (observabilidade)**. Esta iteração expõe **métricas Prometheus**:
métricas HTTP automáticas (contagem/latência por rota) via
**prometheus-fastapi-instrumentator** + **métricas de negócio** (movimentações,
alertas, jobs de relatório) via **prometheus_client**, num endpoint `/metrics`.

Não sobe stack de scrape (Prometheus/Grafana no compose) nesta fatia — fica para
depois. Sem mudança de schema. Branch parte de `main`.

## Decisões fechadas

- **HTTP:** `prometheus-fastapi-instrumentator` instrumenta a app e expõe
  `/metrics` (formato texto Prometheus).
- **Negócio:** `prometheus_client` Counters definidos num módulo central
  (`app/core/metrics.py`), incrementados nos serviços.
- **Endpoint:** `/metrics` na raiz (fora de `/api/v1`), **sem autenticação**
  (padrão de scrape; protegido em rede), como o `/health`.
- **Toggle:** `METRICS_ENABLED: bool = True` em `Settings` — desliga toda a
  instrumentação quando `false`.
- **Registry único (default):** HTTP e negócio no mesmo registry global, para
  saírem juntos no `/metrics`. `setup_metrics(app)` é **idempotente** (tolera
  múltiplas instâncias de app nos testes sem erro de timeseries duplicada).
- **Sem stack de scrape** no compose nesta iteração.

## Métricas de negócio

| Métrica | Tipo | Labels | Onde incrementa |
|---------|------|--------|-----------------|
| `stockguardian_movements_total` | Counter | `type` (in/out/adjustment) | `MovementService.create` (pós-commit) |
| `stockguardian_alerts_opened_total` | Counter | `kind` (low_stock/overstock) | `AlertService.evaluate` (ao abrir) |
| `stockguardian_alerts_resolved_total` | Counter | `kind` | `AlertService.evaluate` (ao resolver) |
| `stockguardian_report_jobs_enqueued_total` | Counter | `report` (inventory_valuation/movements_summary) | `ReportJobQueue.enqueue_*` |

> Os incrementos de alerta espelham os logs `alert_opened`/`alert_resolved` (mesmo
> ponto, antes do commit do orquestrador) — caveat menor de over-count se a
> transação falhar depois; aceitável no escopo. Movimentações incrementam
> pós-commit.

As métricas HTTP automáticas (do instrumentator) cobrem
`http_requests_total`, `http_request_duration_seconds`, etc. com labels de
método/handler/status.

## Componentes

### Dependências (`pyproject.toml`, runtime)
- `prometheus-fastapi-instrumentator>=7.0.0` (traz `prometheus-client`).

### Config (`app/core/config.py` + `.env.example`)
- `METRICS_ENABLED: bool = True`.

### `app/core/metrics.py`
```python
from prometheus_client import Counter

MOVEMENTS_TOTAL = Counter("stockguardian_movements_total", "...", ["type"])
ALERTS_OPENED_TOTAL = Counter("stockguardian_alerts_opened_total", "...", ["kind"])
ALERTS_RESOLVED_TOTAL = Counter("stockguardian_alerts_resolved_total", "...", ["kind"])
REPORT_JOBS_ENQUEUED_TOTAL = Counter(
    "stockguardian_report_jobs_enqueued_total", "...", ["report"]
)


def setup_metrics(app: FastAPI) -> None:
    """Instala o instrumentator HTTP e expõe /metrics. Idempotente p/ testes."""
    instrumentator = Instrumentator()
    try:
        instrumentator.instrument(app)
    except ValueError:
        pass  # métricas já registradas no processo (múltiplos create_app)
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
```
> O mecanismo exato de idempotência (try/except no registry vs. guarda) será
> fechado na implementação, **validado localmente** chamando `create_app()` duas
> vezes e batendo em `/metrics` (não exige DB).

### Integração nos serviços
- `MovementService.create`: após o `commit`/log →
  `MOVEMENTS_TOTAL.labels(type=data.type.value).inc()`.
- `AlertService.evaluate`: após `logger.info("alert_opened", ...)` →
  `ALERTS_OPENED_TOTAL.labels(kind=kind.value).inc()`; idem `alert_resolved` →
  `ALERTS_RESOLVED_TOTAL`.
- `ReportJobQueue.enqueue_inventory_valuation` / `enqueue_movements_summary`:
  após obter o `job_id` → `REPORT_JOBS_ENQUEUED_TOTAL.labels(report=...).inc()`.

### `app/main.py`
- em `create_app`, após registrar rotas: `if settings.METRICS_ENABLED: setup_metrics(app)`.

## Arquivos

**Novos:** `app/core/metrics.py`, `tests/unit/test_metrics.py`,
`tests/integration/test_metrics_endpoint.py`.

**Editados:** `pyproject.toml`, `app/core/config.py`, `.env.example`,
`app/main.py`, `app/services/movement.py`, `app/services/alert.py`,
`app/services/report_jobs.py`, `README.md`.

## Testes

**Unit** (`test_metrics.py`, sem DB):
- incrementar cada Counter (`.labels(...).inc()`) e ler o valor via
  `counter.labels(...)._value.get()` (ou `REGISTRY.get_sample_value`) → +1.
- `create_app()` duas vezes com `METRICS_ENABLED=True` **não** levanta erro
  (idempotência) e ambas expõem a rota `/metrics`.

**Integration** (`test_metrics_endpoint.py`, Postgres real):
- `GET /metrics` (sem auth) → 200, content-type texto Prometheus; corpo contém
  os nomes das métricas custom e `http_requests_total`.
- após `POST /movements` (in) → `/metrics` mostra
  `stockguardian_movements_total{type="in"}` com valor ≥ 1.
- (sanity) `/metrics` acessível sem token.

**Gates:** ruff + ruff format + mypy strict + pytest verdes.

## Verificação

- `ruff`/`mypy`/`pytest` (unit local; integração no Docker).
- **Local sem DB:** script que cria a app 2× e faz `GET /metrics` via
  `httpx.ASGITransport` → 200 e métricas presentes (prova idempotência).
- `docker compose up --build`: `GET /metrics` retorna as métricas; após algumas
  requisições/movimentações os contadores sobem.

## Fora de escopo (próximas iterações da Fase 4)

- Stack de scrape no compose (Prometheus + Grafana + dashboards).
- Health/readiness probes separando liveness de readiness (DB/Redis).
- Tracing OpenTelemetry (spans + OTLP).
- Métricas do worker ARQ (processo separado; expõe seu próprio endpoint).
- Deploy/manifests e pipeline de CD.
