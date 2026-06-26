# Dashboard Operacional — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Endpoint `GET /dashboard/summary` (MANAGER+) com contadores gerais (produtos/fornecedores ativos, usuários), servido com cache-aside no Redis (TTL 60s).

**Architecture:** Helper genérico `cache.get_or_set` (cache-aside) + `DashboardService` que orquestra os COUNTs reusando `BaseRepository.count`. Rota fina injeta sessão + Redis. Sem cache inline no serviço, sem decorator.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Redis (redis.asyncio / fakeredis nos testes), Pydantic v2, pytest. Segue os padrões da Fase 1.

Spec: `docs/superpowers/specs/2026-06-26-dashboard-operacional-design.md`.

---

## Convenção de testes (ambiente)

Igual às iterações anteriores: app/testes em container 3.13 contra Postgres real.

**Subir infra (uma vez):**
```bash
cd /Users/viniciusoliveira/Documents/stockguardian
cp -n .env.example .env
docker compose -f docker/docker-compose.yml up -d db redis
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian -c "CREATE DATABASE stockguardian_test;" 2>/dev/null || true
```

**Atalho TESTRUN `<CMD>`:**
```bash
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
docker run --rm --network stockguardian_default -v "$PWD":/app -w /app \
  -e TEST_DATABASE_URL="postgresql+asyncpg://stockguardian:stockguardian@db:5432/stockguardian_test" \
  -e SECRET_KEY="ci-test-secret" \
  python:3.13-slim bash -c "pip install -q uv && uv pip install --system -q '.[dev]' && <CMD>"
```

---

## Task 1: Config — TTL do cache

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Adicionar setting**

Em `app/core/config.py`, na classe `Settings`, junto dos demais campos de
aplicação (ex.: após `LOG_JSON: bool = True`), adicionar:
```python
    DASHBOARD_CACHE_TTL: int = 60  # segundos
```

- [ ] **Step 2: Documentar no .env.example**

Em `.env.example`, na seção da aplicação, adicionar a linha:
```
DASHBOARD_CACHE_TTL=60
```

- [ ] **Step 3: Verificar**

TESTRUN `python -c "from app.core.config import settings; print(settings.DASHBOARD_CACHE_TTL)"`
Expected: `60`.

- [ ] **Step 4: Commit**
```bash
git add app/core/config.py .env.example
git commit -m "feat(dashboard): setting DASHBOARD_CACHE_TTL"
```

---

## Task 2: Helper cache-aside `get_or_set`

**Files:**
- Create: `app/core/cache.py`
- Test: `tests/unit/test_cache.py`

- [ ] **Step 1: Escrever os testes falhos**

`tests/unit/test_cache.py`:
```python
"""Testes unitários do helper de cache-aside (fakeredis, sem DB)."""

from __future__ import annotations

import pytest
from fakeredis import aioredis as fake_aioredis

from app.core.cache import get_or_set

pytestmark = pytest.mark.unit


@pytest.fixture
async def redis():
    client = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


async def test_miss_calls_factory_and_caches(redis) -> None:
    calls = {"n": 0}

    async def factory() -> dict:
        calls["n"] += 1
        return {"value": 42}

    result = await get_or_set(redis, "k", 60, factory)
    assert result == {"value": 42}
    assert calls["n"] == 1
    assert await redis.get("k") is not None


async def test_hit_skips_factory(redis) -> None:
    calls = {"n": 0}

    async def factory() -> dict:
        calls["n"] += 1
        return {"value": 1}

    await get_or_set(redis, "k", 60, factory)  # miss -> popula
    result = await get_or_set(redis, "k", 60, factory)  # hit
    assert result == {"value": 1}
    assert calls["n"] == 1  # factory chamada só uma vez


async def test_sets_ttl(redis) -> None:
    async def factory() -> dict:
        return {"v": 1}

    await get_or_set(redis, "k", 30, factory)
    ttl = await redis.ttl("k")
    assert 0 < ttl <= 30
```

- [ ] **Step 2: Rodar — deve falhar**

TESTRUN `pytest tests/unit/test_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: app.core.cache`.

- [ ] **Step 3: Implementar o helper**

`app/core/cache.py`:
```python
"""Helper de cache-aside sobre Redis.

Padrão get-or-set: tenta o cache; no miss, computa via `factory`, grava como
JSON com TTL e retorna. Reutilizável por qualquer endpoint cacheável.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis


async def get_or_set(
    redis: Redis,
    key: str,
    ttl: int,
    factory: Callable[[], Awaitable[dict]],
) -> dict:
    cached = await redis.get(key)
    if cached is not None:
        result: dict = json.loads(cached)
        return result
    value = await factory()
    await redis.set(key, json.dumps(value), ex=ttl)
    return value
```

- [ ] **Step 4: Rodar — deve passar**

TESTRUN `pytest tests/unit/test_cache.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**
```bash
git add app/core/cache.py tests/unit/test_cache.py
git commit -m "feat(dashboard): helper cache-aside get_or_set + unit tests"
```

---

## Task 3: Schema DashboardSummary

**Files:**
- Create: `app/schemas/dashboard.py`

- [ ] **Step 1: Escrever o schema**

`app/schemas/dashboard.py`:
```python
from __future__ import annotations

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    active_products: int
    active_suppliers: int
    total_users: int
```

- [ ] **Step 2: Verificar**

TESTRUN `python -c "from app.schemas.dashboard import DashboardSummary; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/schemas/dashboard.py
git commit -m "feat(dashboard): schema DashboardSummary"
```

---

## Task 4: DashboardService

**Files:**
- Create: `app/services/dashboard.py`

- [ ] **Step 1: Escrever o serviço**

`app/services/dashboard.py`:
```python
"""Serviço do dashboard operacional.

Calcula contadores gerais e serve com cache-aside no Redis.
"""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_or_set
from app.core.config import settings
from app.repositories.product import ProductRepository
from app.repositories.supplier import SupplierRepository
from app.repositories.user import UserRepository

_SUMMARY_CACHE_KEY = "dashboard:summary"


class DashboardService:
    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self.session = session
        self.redis = redis

    async def summary(self) -> dict:
        async def factory() -> dict:
            return {
                "active_products": await ProductRepository(self.session).count(is_active=True),
                "active_suppliers": await SupplierRepository(self.session).count(is_active=True),
                "total_users": await UserRepository(self.session).count(),
            }

        return await get_or_set(
            self.redis, _SUMMARY_CACHE_KEY, settings.DASHBOARD_CACHE_TTL, factory
        )
```

> `BaseRepository.count(**filters)` já existe (Fase 1) e aceita `is_active=True`.

- [ ] **Step 2: Verificar import**

TESTRUN `python -c "from app.services.dashboard import DashboardService; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/services/dashboard.py
git commit -m "feat(dashboard): DashboardService com cache-aside"
```

---

## Task 5: Rota /dashboard/summary

**Files:**
- Create: `app/api/v1/routes/dashboard.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Escrever a rota**

`app/api/v1/routes/dashboard.py`:
```python
"""Rotas do dashboard operacional."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_role
from app.dependencies.db import DBSession, RedisClient
from app.models.user import UserRole
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_role(UserRole.MANAGER))],
)


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(session: DBSession, redis: RedisClient) -> DashboardSummary:
    data = await DashboardService(session, redis).summary()
    return DashboardSummary.model_validate(data)
```

- [ ] **Step 2: Registrar o router**

Em `app/api/v1/router.py`, importar `dashboard` e incluir o router:
```python
from app.api.v1.routes import auth, dashboard, movements, products, suppliers, users
...
api_router.include_router(dashboard.router)
```

- [ ] **Step 3: Verificar boot**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**
```bash
git add app/api/v1/routes/dashboard.py app/api/v1/router.py
git commit -m "feat(dashboard): rota GET /dashboard/summary (MANAGER+)"
```

---

## Task 6: Testes de integração

**Files:**
- Test: `tests/integration/test_dashboard.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_dashboard.py`:
```python
"""Integração: dashboard de contadores gerais (com cache Redis)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _make_supplier(auth_client: AsyncClient) -> str:
    doc = str(uuid.uuid4().int)[:14]
    resp = await auth_client.post(f"{PREFIX}/suppliers", json={"name": "F", "document": doc})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_product(auth_client: AsyncClient, supplier_id: str, *, active: bool = True) -> str:
    sku = "P-" + uuid.uuid4().hex[:6]
    resp = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": sku, "name": "X", "supplier_id": supplier_id},
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    if not active:
        patch = await auth_client.patch(f"{PREFIX}/products/{pid}", json={"is_active": False})
        assert patch.status_code == 200, patch.text
    return pid


async def test_summary_counts(auth_client: AsyncClient) -> None:
    sid = await _make_supplier(auth_client)
    await _make_product(auth_client, sid, active=True)
    await _make_product(auth_client, sid, active=False)  # inativo não conta

    resp = await auth_client.get(f"{PREFIX}/dashboard/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active_products"] == 1
    assert body["active_suppliers"] == 1
    assert body["total_users"] >= 1  # admin do auth_client


async def test_summary_is_cached(auth_client: AsyncClient) -> None:
    sid = await _make_supplier(auth_client)
    await _make_product(auth_client, sid, active=True)

    first = (await auth_client.get(f"{PREFIX}/dashboard/summary")).json()
    assert first["active_products"] == 1

    # Cria outro produto; dentro do TTL o valor servido continua o cacheado.
    await _make_product(auth_client, sid, active=True)
    second = (await auth_client.get(f"{PREFIX}/dashboard/summary")).json()
    assert second["active_products"] == 1  # ainda do cache


async def test_requires_auth(client: AsyncClient) -> None:
    resp = await client.get(f"{PREFIX}/dashboard/summary")
    assert resp.status_code == 401
```

- [ ] **Step 2: Rodar — deve passar**

TESTRUN `pytest tests/integration/test_dashboard.py -q`
Expected: PASS (3 passed).

> Observação: `test_summary_is_cached` depende do `redis_client` (fakeredis) ser
> o mesmo na vida do `client` — já garantido pela fixture `client` da Fase 1, que
> injeta um único `redis_client` por teste.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_dashboard.py
git commit -m "test(dashboard): integração contadores + cache"
```

---

## Task 7: Verificação final + docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar README**

Na tabela de endpoints do `README.md`, adicionar:
```markdown
| GET | `/dashboard/summary` | Contadores gerais (cache Redis) | MANAGER+ |
```

- [ ] **Step 2: Rodar todos os gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: ruff All checks passed, mypy Success, pytest todos verdes.

- [ ] **Step 3: Validar end-to-end no stack**

```bash
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
docker compose -f docker/docker-compose.yml up -d --build api
sleep 7
docker compose -f docker/docker-compose.yml exec -T api python -m scripts.seed >/dev/null 2>&1
# login MANAGER (admin do seed é ADMIN, que passa em require_role(MANAGER))
TOK=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@stockguardian.com","password":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s http://localhost:8000/api/v1/dashboard/summary -H "Authorization: Bearer $TOK"
```
Expected: JSON com `active_products`, `active_suppliers`, `total_users` (do seed: 3 produtos, 1 fornecedor, 1 usuário).

- [ ] **Step 4: Commit + push + PR**
```bash
git add README.md
git commit -m "docs(dashboard): endpoint /dashboard/summary no README"
git push -u origin feat/operational-dashboard
```
Abrir PR pela URL retornada no push.

---

## Self-review

- **Cobertura do spec:** setting TTL (T1), helper get_or_set (T2), schema (T3),
  DashboardService com cache-aside (T4), rota MANAGER+ + router (T5), testes
  unit+integração incl. prova de cache e 401 (T6), gates+README+e2e (T7). ✔
- **Placeholders:** nenhum — todo passo tem código/comando.
- **Consistência de tipos:** `get_or_set(redis, key, ttl, factory)` (T2) usado
  por `DashboardService.summary` (T4); `DashboardSummary` (T3) usado em T5/T6;
  `DashboardService(session, redis)` (T4) usado na rota (T5). ✔
- **Nota:** 403 para OPERATOR não é testado (fixture `auth_client` força admin) —
  documentado no spec.
