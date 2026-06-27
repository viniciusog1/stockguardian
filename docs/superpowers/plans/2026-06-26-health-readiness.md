# Health/Readiness Probes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar liveness (`/health`) de readiness (`/health/ready`), checando DB
e Redis de verdade (200/503). Sem migration, sem autenticação nas probes.

**Architecture:** `HealthService` (checks DB/Redis) + schemas + router raiz
(`app/api/health.py`); `main.py` registra o router e remove o `/health` inline.

**Tech Stack:** FastAPI, SQLAlchemy async, redis async, pytest.

Spec: `docs/superpowers/specs/2026-06-26-health-readiness-design.md`.

---

## Convenção de testes (ambiente)

Unit roda local (fakes, sem I/O). Integração com Postgres no Docker do dev.

---

## Task 1: Schemas + serviço de health + unit

**Files:**
- Create: `app/schemas/health.py`
- Create: `app/services/health.py`
- Create: `tests/unit/test_health.py`

- [ ] **Step 1: Schemas**

`app/schemas/health.py`:
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: str
    service: str


class CheckResult(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: dict[str, CheckResult]
```

- [ ] **Step 2: Serviço**

`app/services/health.py`:
```python
"""Serviço de health/readiness: checa dependências (DB, Redis)."""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.health import CheckResult, ReadinessResponse


class HealthService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis

    async def _check_db(self) -> CheckResult:
        try:
            await self.session.execute(text("SELECT 1"))
            return CheckResult(status="ok")
        except Exception as exc:  # noqa: BLE001 - readiness reporta, não propaga
            return CheckResult(status="error", detail=str(exc))

    async def _check_redis(self) -> CheckResult:
        try:
            await self.redis.ping()
            return CheckResult(status="ok")
        except Exception as exc:  # noqa: BLE001
            return CheckResult(status="error", detail=str(exc))

    async def readiness(self) -> ReadinessResponse:
        checks = {
            "database": await self._check_db(),
            "redis": await self._check_redis(),
        }
        ready = all(c.status == "ok" for c in checks.values())
        return ReadinessResponse(ready=ready, checks=checks)
```
> Se o ruff não tiver a regra BLE habilitada, remover os `# noqa: BLE001`
> (verificar no Step de gates; `warn_unused_ignores` do mypy não afeta noqa do
> ruff, mas o ruff acusa noqa inútil via RUF100). Decidir no Step 4.

- [ ] **Step 3: Unit**

`tests/unit/test_health.py`:
```python
"""Unit: HealthService (checks com fakes, sem I/O real)."""

from __future__ import annotations

import pytest
from app.services.health import HealthService

pytestmark = pytest.mark.unit


class _OkSession:
    async def execute(self, *_: object) -> None:
        return None


class _FailSession:
    async def execute(self, *_: object) -> None:
        raise RuntimeError("db down")


class _OkRedis:
    async def ping(self) -> bool:
        return True


class _FailRedis:
    async def ping(self) -> bool:
        raise RuntimeError("redis down")


async def test_ready_when_all_ok() -> None:
    svc = HealthService(_OkSession(), _OkRedis())  # type: ignore[arg-type]
    result = await svc.readiness()
    assert result.ready is True
    assert result.checks["database"].status == "ok"
    assert result.checks["redis"].status == "ok"


async def test_not_ready_when_redis_down() -> None:
    svc = HealthService(_OkSession(), _FailRedis())  # type: ignore[arg-type]
    result = await svc.readiness()
    assert result.ready is False
    assert result.checks["redis"].status == "error"
    assert result.checks["database"].status == "ok"


async def test_not_ready_when_db_down() -> None:
    svc = HealthService(_FailSession(), _OkRedis())  # type: ignore[arg-type]
    result = await svc.readiness()
    assert result.ready is False
    assert result.checks["database"].status == "error"
```
> Os testes são `async`; o projeto usa `asyncio_mode = "auto"`, então rodam sem
> marcador extra. Marcador `unit` mantido por consistência.

- [ ] **Step 4: Rodar unit + ruff**

TESTRUN `pytest tests/unit/test_health.py -q`
TESTRUN `ruff check app/services/health.py tests/unit/test_health.py`
Expected: PASS + ruff limpo (ajustar `# noqa` conforme as regras ativas).

- [ ] **Step 5: Commit**
```bash
git add app/schemas/health.py app/services/health.py tests/unit/test_health.py
git commit -m "feat(health): HealthService + schemas de readiness (unit)"
```

---

## Task 2: Router de health + wiring no main

**Files:**
- Create: `app/api/health.py`
- Modify: `app/main.py`

- [ ] **Step 1: Router**

`app/api/health.py`:
```python
"""Probes de liveness e readiness (raiz, sem autenticação)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.dependencies.db import DBSession, RedisClient
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=LivenessResponse, summary="Liveness probe")
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok", service=settings.PROJECT_NAME)


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(
    session: DBSession, redis: RedisClient, response: Response
) -> ReadinessResponse:
    result = await HealthService(session, redis).readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
```

- [ ] **Step 2: main.py**

Em `app/main.py`:
- import: `from app.api import health`.
- remover o bloco `@app.get("/health", ...)` inline (a função `health()`).
- após `app.include_router(api_router, prefix=settings.API_V1_PREFIX)`:
```python
    app.include_router(health.router)
```
(antes do `if settings.METRICS_ENABLED: setup_metrics(app)`).

- [ ] **Step 3: Boot + paths + mypy**

TESTRUN `python -c "from app.main import create_app; app=create_app(); print(sorted(p for r in [getattr(x,'path','') for x in app.routes] for p in [r] if 'health' in p))"`
Expected: `['/health', '/health/ready']`.
TESTRUN `mypy app`
Expected: Success.

- [ ] **Step 4: Commit**
```bash
git add app/api/health.py app/main.py
git commit -m "feat(health): /health (liveness) + /health/ready (readiness, 503)"
```

---

## Task 3: Integração

**Files:**
- Create: `tests/integration/test_health.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_health.py`:
```python
"""Integração: probes de liveness e readiness."""

from __future__ import annotations

import pytest
from app.dependencies.db import get_redis_client
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_readiness_ok(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


async def test_readiness_503_when_redis_down(client: AsyncClient) -> None:
    class _FailRedis:
        async def ping(self) -> bool:
            raise RuntimeError("redis down")

    app = client._app  # type: ignore[attr-defined]
    app.dependency_overrides[get_redis_client] = lambda: _FailRedis()
    try:
        resp = await client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_redis_client, None)
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["checks"]["redis"]["status"] == "error"
    assert body["checks"]["database"]["status"] == "ok"
```

- [ ] **Step 2: Rodar**

TESTRUN `pytest tests/integration/test_health.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_health.py
git commit -m "test(health): liveness + readiness (200/503)"
```

---

## Task 4: README + gates finais

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README**

- tabela de endpoints: trocar/atualizar a linha de health e adicionar readiness:
```markdown
| GET | `/health` | Liveness probe | público |
| GET | `/health/ready` | Readiness probe (checa DB + Redis; 503 se indisponível) | público |
```
- roadmap Fase 4:
```markdown
- [ ] **Fase 4**: ~~métricas Prometheus~~ ✅ · ~~health/readiness~~ ✅ · tracing OpenTelemetry · deploy/monitoramento
```

- [ ] **Step 2: Gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: tudo verde.

- [ ] **Step 3: Validar no Docker (dev)**

```bash
docker compose -f docker/docker-compose.yml up -d --build
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/health        # 200
curl -s localhost:8000/health/ready                                    # ready=true
docker compose -f docker/docker-compose.yml stop redis
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/health/ready   # 503
```

- [ ] **Step 4: Commit + push**
```bash
git add README.md
git commit -m "docs(health): probes de liveness/readiness + Fase 4 atualizada"
git push -u origin feat/health-readiness
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** schemas + HealthService + unit (T1), router raiz +
  wiring/remoção do inline (T2), integração 200/503 + sem auth (T3), README+gates
  (T4). ✔
- **Placeholders:** nenhum.
- **Consistência:** `ReadinessResponse`/`CheckResult` (T1) usados no serviço (T1) e
  no router (T2) e nos testes (T1/T3); `DBSession`/`RedisClient` reusados; status
  503 setado via `response.status_code` mantendo o `response_model`.
- **Sem migration / sem nova permissão / sem auth nas probes.**
- **Nota:** liveness mantém o shape atual; readiness adiciona detalhe por
  dependência. Uso das probes nos healthchecks do compose fica para a fatia de
  deploy.
