# Métricas Prometheus — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor `/metrics` (Prometheus) com métricas HTTP automáticas
(prometheus-fastapi-instrumentator) + métricas de negócio (prometheus_client)
para movimentações, alertas e jobs de relatório. Toggle por `METRICS_ENABLED`.
Sem migration.

**Architecture:** `app/core/metrics.py` define os Counters de negócio e
`setup_metrics(app)` (instrumentator + expose `/metrics`, idempotente). Serviços
incrementam os Counters. `create_app` chama `setup_metrics` quando habilitado.

**Tech Stack:** prometheus-fastapi-instrumentator, prometheus_client, FastAPI,
pytest.

Spec: `docs/superpowers/specs/2026-06-26-metricas-prometheus-design.md`.

---

## Convenção de testes (ambiente)

Unit roda local (sem DB). A idempotência do `/metrics` é validada localmente
(2× `create_app` + GET via ASGITransport). Integração com Postgres no Docker do
dev (como nas iterações anteriores).

---

## Task 1: Dependência + config

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Dependência**

`pyproject.toml`, `[project].dependencies`:
```toml
    "prometheus-fastapi-instrumentator>=7.0.0",
```

- [ ] **Step 2: Toggle**

`app/core/config.py` (seção Aplicação):
```python
    METRICS_ENABLED: bool = True
```
`.env.example` (seção Aplicação):
```
METRICS_ENABLED=true
```

- [ ] **Step 3: Instalar + import**

TESTRUN `python -c "import prometheus_fastapi_instrumentator, prometheus_client; print('ok')"`

- [ ] **Step 4: Commit**
```bash
git add pyproject.toml app/core/config.py .env.example
git commit -m "build(metrics): prometheus-fastapi-instrumentator + METRICS_ENABLED"
```

---

## Task 2: Módulo de métricas + wiring + unit (idempotência)

**Files:**
- Create: `app/core/metrics.py`
- Modify: `app/main.py`
- Create: `tests/unit/test_metrics.py`

- [ ] **Step 1: metrics.py**

`app/core/metrics.py`:
```python
"""Métricas Prometheus: Counters de negócio + setup do instrumentator HTTP."""

from __future__ import annotations

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
    """Instrumenta a app (HTTP) e expõe /metrics. Idempotente entre instâncias."""
    instrumentator = Instrumentator()
    try:
        instrumentator.instrument(app)
    except ValueError:
        # métricas HTTP já registradas no processo (ex.: múltiplos create_app em testes)
        pass
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
```

- [ ] **Step 2: Wiring no main**

`app/main.py`:
- import: `from app.core.metrics import setup_metrics`.
- em `create_app`, após `app.include_router(api_router, ...)` e o `@app.get("/health")`:
```python
    if settings.METRICS_ENABLED:
        setup_metrics(app)
```

- [ ] **Step 3: Unit (idempotência + counters)**

`tests/unit/test_metrics.py`:
```python
"""Unit: counters de negócio e idempotência do setup de métricas."""

from __future__ import annotations

import pytest
from app.core.metrics import MOVEMENTS_TOTAL
from app.main import create_app

pytestmark = pytest.mark.unit


def test_counter_increments() -> None:
    before = MOVEMENTS_TOTAL.labels(type="in")._value.get()
    MOVEMENTS_TOTAL.labels(type="in").inc()
    after = MOVEMENTS_TOTAL.labels(type="in")._value.get()
    assert after == before + 1


def test_create_app_twice_is_idempotent() -> None:
    a1 = create_app()
    a2 = create_app()
    for app in (a1, a2):
        assert any(getattr(r, "path", "") == "/metrics" for r in app.routes)
```

- [ ] **Step 4: Rodar unit + validar idempotência via HTTP (sem DB)**

TESTRUN `pytest tests/unit/test_metrics.py -q`
Validação local extra (sem DB), via ASGITransport:
```python
import anyio, httpx
from app.main import create_app
async def go():
    create_app()  # 1ª
    app = create_app()  # 2ª
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/metrics")
        print(r.status_code, "stockguardian_movements_total" in r.text or "http_requests" in r.text)
anyio.run(go)
```
Expected: `200 True` (sem erro de timeseries duplicada).

> Se `instrument()` não levantar/duplicar de forma tratável, ajustar
> `setup_metrics` (ex.: guarda de instrumentação única + expose por app) até o
> cenário 2× passar. Decisão fechada nesta etapa, com teste real.

- [ ] **Step 5: Commit**
```bash
git add app/core/metrics.py app/main.py tests/unit/test_metrics.py
git commit -m "feat(metrics): /metrics (instrumentator) + counters de negócio"
```

---

## Task 3: Instrumentar os serviços

**Files:**
- Modify: `app/services/movement.py`
- Modify: `app/services/alert.py`
- Modify: `app/services/report_jobs.py`

- [ ] **Step 1: Movimentações**

Em `app/services/movement.py`:
- import: `from app.core.metrics import MOVEMENTS_TOTAL`.
- em `create`, após `self.session.refresh(movement)` e o `logger.info("stock_movement", ...)`:
```python
        MOVEMENTS_TOTAL.labels(type=data.type.value).inc()
```

- [ ] **Step 2: Alertas**

Em `app/services/alert.py`:
- import: `from app.core.metrics import ALERTS_OPENED_TOTAL, ALERTS_RESOLVED_TOTAL`.
- após `logger.info("alert_opened", ...)`:
```python
                ALERTS_OPENED_TOTAL.labels(kind=kind.value).inc()
```
- após `logger.info("alert_resolved", ...)`:
```python
                ALERTS_RESOLVED_TOTAL.labels(kind=kind.value).inc()
```

- [ ] **Step 3: Jobs de relatório**

Em `app/services/report_jobs.py`:
- import: `from app.core.metrics import REPORT_JOBS_ENQUEUED_TOTAL`.
- em `enqueue_inventory_valuation`, após `job_id = _require_job_id(job)` (refatorar
  para guardar o id antes do return):
```python
        job_id = _require_job_id(job)
        REPORT_JOBS_ENQUEUED_TOTAL.labels(report="inventory_valuation").inc()
        return job_id
```
- idem `enqueue_movements_summary` com `report="movements_summary"`.

- [ ] **Step 4: Boot + mypy**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
TESTRUN `mypy app`
Expected: `ok` + mypy Success.

- [ ] **Step 5: Commit**
```bash
git add app/services/movement.py app/services/alert.py app/services/report_jobs.py
git commit -m "feat(metrics): incrementa counters em movimentações, alertas e jobs"
```

---

## Task 4: Integração do /metrics

**Files:**
- Create: `tests/integration/test_metrics_endpoint.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_metrics_endpoint.py`:
```python
"""Integração: endpoint /metrics (Prometheus)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def test_metrics_open_and_lists_names(client: AsyncClient) -> None:
    resp = await client.get("/metrics")  # sem auth
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "stockguardian_movements_total" in body
    assert "http_requests_total" in body or "http_request" in body


async def test_movement_increments_counter(auth_client: AsyncClient) -> None:
    doc = str(uuid.uuid4().int)[:14]
    sid = (
        await auth_client.post(f"{PREFIX}/suppliers", json={"name": "F", "document": doc})
    ).json()["id"]
    pid = (
        await auth_client.post(
            f"{PREFIX}/products", json={"sku": "M-" + uuid.uuid4().hex[:6], "name": "P", "supplier_id": sid}
        )
    ).json()["id"]
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 3}
    )

    body = (await auth_client.get("/metrics")).text
    assert 'stockguardian_movements_total{type="in"}' in body
```

- [ ] **Step 2: Rodar**

TESTRUN `pytest tests/integration/test_metrics_endpoint.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_metrics_endpoint.py
git commit -m "test(metrics): /metrics aberto + counter de movimentação"
```

---

## Task 5: README + gates finais

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README**

- tabela de endpoints (ou seção própria), adicionar:
```markdown
| GET | `/metrics` | Métricas Prometheus (HTTP + negócio) | público (scrape) |
```
- Stack: acrescentar "Métricas | Prometheus (prometheus-fastapi-instrumentator)".
- iniciar a Fase 4 no roadmap:
```markdown
- [ ] **Fase 4**: ~~métricas Prometheus~~ ✅ · health/readiness · tracing OTel · deploy
```

- [ ] **Step 2: Gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: tudo verde.

- [ ] **Step 3: Validar no Docker (dev)**

```bash
docker compose -f docker/docker-compose.yml up -d --build
curl -s localhost:8000/metrics | grep stockguardian_
```

- [ ] **Step 4: Commit + push**
```bash
git add README.md
git commit -m "docs(metrics): /metrics + Fase 4 iniciada"
git push -u origin feat/prometheus-metrics
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** deps+toggle (T1), metrics.py + /metrics idempotente +
  unit de idempotência/counter (T2), instrumentação dos 3 serviços (T3),
  integração /metrics aberto + incremento (T4), README+gates (T5). ✔
- **Placeholders:** nenhum.
- **Consistência:** Counters definidos em `app/core/metrics.py` (T2) e usados nos
  serviços (T3) e nos testes (T2/T4); `setup_metrics` chamado em `create_app`
  sob `METRICS_ENABLED` (T2); `/metrics` sem auth (fora do api_router).
- **Sem migration / sem nova permissão.**
- **Risco endereçado:** múltiplos `create_app` nos testes podem duplicar séries no
  registry — `setup_metrics` idempotente, validado localmente (T2-step4) antes de
  prosseguir.
