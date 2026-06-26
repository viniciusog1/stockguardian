# Relatórios Operacionais — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar dois relatórios operacionais read-only sob `/reports` —
**valuation de estoque** e **resumo de movimentações** — com nova permissão
`report:read` (MANAGER+), SQL de agregação nos repositórios e formato tabular
(linhas + resumo) pronto para o export Excel da próxima iteração.

**Architecture:** `ReportService` orquestra; `ProductRepository.inventory_valuation`
e `MovementRepository.summary_by_type` emitem o SQL. Schemas em
`app/schemas/report.py`, rotas em `app/api/v1/routes/reports.py`. Lógica pura
(`build_movement_summary_rows`) testada em unit.

**Tech Stack:** SQLAlchemy 2 async, FastAPI, Pydantic v2, pytest. Segue os padrões
das fases anteriores. Sem migration (nenhuma mudança de schema do banco).

Spec: `docs/superpowers/specs/2026-06-26-relatorios-operacionais-design.md`.

---

## Convenção de testes (ambiente)

**Subir infra (uma vez), a partir da raiz do projeto:**
```bash
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

> Sem Docker disponível, rode localmente com um Postgres de teste e
> `TEST_DATABASE_URL` apontando para ele (`uv pip install '.[dev]'`).

---

## Task 1: RBAC — permissão report:read

**Files:**
- Modify: `app/core/permissions.py`
- Modify: `tests/unit/test_permissions.py`

- [ ] **Step 1: Adicionar REPORT_READ ao enum e ao MANAGER**

Em `app/core/permissions.py`:
- adicionar ao enum `Permission` (após `DASHBOARD_READ`):
```python
    REPORT_READ = "report:read"
```
- incluir no conjunto `_MANAGER`:
```python
_MANAGER: frozenset[Permission] = _OPERATOR | frozenset(
    {
        Permission.SUPPLIER_WRITE,
        Permission.PRODUCT_WRITE,
        Permission.ALERT_RESOLVE,
        Permission.DASHBOARD_READ,
        Permission.REPORT_READ,
    }
)
```

- [ ] **Step 2: Cobrir no teste de permissões**

Em `tests/unit/test_permissions.py`, acrescentar asserts de que MANAGER e ADMIN
têm `REPORT_READ` e OPERATOR não. (Seguir o estilo dos testes já existentes no
arquivo; adicionar onde houver as asserções por role.)

- [ ] **Step 3: Rodar unit de permissões**

TESTRUN `pytest tests/unit/test_permissions.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**
```bash
git add app/core/permissions.py tests/unit/test_permissions.py
git commit -m "feat(reports): permissão report:read (MANAGER+)"
```

---

## Task 2: Repositórios — agregações

**Files:**
- Modify: `app/repositories/product.py`
- Modify: `app/repositories/movement.py`

- [ ] **Step 1: ProductRepository.inventory_valuation**

Em `app/repositories/product.py`:
- ajustar imports:
```python
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import Row, select
```
- adicionar o método (linhas ordenadas por valor desc; `stock_value` calculado no SQL):
```python
    async def inventory_valuation(
        self, *, supplier_id: uuid.UUID | None = None, only_active: bool = True
    ) -> Sequence[Row[tuple[uuid.UUID, str, str, int, Decimal, Decimal]]]:
        """Linhas de valuation: produto + valor parado em estoque (quantity * preço)."""
        stock_value = (Product.quantity * Product.unit_price).label("stock_value")
        stmt = select(
            Product.id,
            Product.sku,
            Product.name,
            Product.quantity,
            Product.unit_price,
            stock_value,
        )
        if only_active:
            stmt = stmt.where(Product.is_active.is_(True))
        if supplier_id is not None:
            stmt = stmt.where(Product.supplier_id == supplier_id)
        stmt = stmt.order_by(stock_value.desc(), Product.sku.asc())
        result = await self.session.execute(stmt)
        return result.all()
```

- [ ] **Step 2: MovementRepository.summary_by_type**

Em `app/repositories/movement.py`:
- ajustar imports:
```python
from collections.abc import Sequence

from sqlalchemy import Row, Select, func, select
```
- adicionar o método (reusa o padrão de filtros do repo):
```python
    async def summary_by_type(
        self,
        *,
        product_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[Row[tuple[MovementType, int, int]]]:
        """Agrega contagem e soma de quantidade por tipo de movimentação no período."""
        stmt = (
            select(
                StockMovement.type,
                func.count().label("movement_count"),
                func.coalesce(func.sum(StockMovement.quantity), 0).label("total_quantity"),
            )
            .group_by(StockMovement.type)
        )
        if product_id is not None:
            stmt = stmt.where(StockMovement.product_id == product_id)
        if date_from is not None:
            stmt = stmt.where(StockMovement.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(StockMovement.created_at <= date_to)
        result = await self.session.execute(stmt)
        return result.all()
```

- [ ] **Step 3: Verificar imports**

TESTRUN `python -c "from app.repositories.product import ProductRepository; from app.repositories.movement import MovementRepository; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**
```bash
git add app/repositories/product.py app/repositories/movement.py
git commit -m "feat(reports): agregações de valuation e resumo de movimentações"
```

---

## Task 3: Schemas dos relatórios

**Files:**
- Create: `app/schemas/report.py`

- [ ] **Step 1: Escrever os schemas**

`app/schemas/report.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.stock_movement import MovementType


class InventoryValuationItem(BaseModel):
    product_id: uuid.UUID
    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    stock_value: Decimal


class InventoryValuationSummary(BaseModel):
    total_products: int
    total_units: int
    total_value: Decimal


class InventoryValuationReport(BaseModel):
    generated_at: datetime
    summary: InventoryValuationSummary
    items: list[InventoryValuationItem]


class MovementsSummaryRow(BaseModel):
    type: MovementType
    movement_count: int
    total_quantity: int


class MovementsSummaryReport(BaseModel):
    generated_at: datetime
    date_from: datetime | None
    date_to: datetime | None
    rows: list[MovementsSummaryRow]
    total_movements: int
```

- [ ] **Step 2: Verificar import**

TESTRUN `python -c "from app.schemas.report import InventoryValuationReport, MovementsSummaryReport; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/schemas/report.py
git commit -m "feat(reports): schemas de valuation e resumo de movimentações"
```

---

## Task 4: Serviço — ReportService + lógica pura

**Files:**
- Create: `app/services/report.py`
- Create: `tests/unit/test_report_logic.py`

- [ ] **Step 1: Escrever os unit tests da lógica pura (deve falhar — módulo não existe)**

`tests/unit/test_report_logic.py`:
```python
"""Testes unitários da normalização do resumo de movimentações (função pura)."""

from __future__ import annotations

import pytest

from app.models.stock_movement import MovementType
from app.services.report import build_movement_summary_rows

pytestmark = pytest.mark.unit


def test_all_types_present() -> None:
    counts = {
        MovementType.IN: (3, 30),
        MovementType.OUT: (2, 12),
        MovementType.ADJUSTMENT: (1, 5),
    }
    rows = build_movement_summary_rows(counts)
    assert [r.type for r in rows] == [MovementType.IN, MovementType.OUT, MovementType.ADJUSTMENT]
    assert (rows[0].movement_count, rows[0].total_quantity) == (3, 30)
    assert (rows[1].movement_count, rows[1].total_quantity) == (2, 12)


def test_missing_types_filled_with_zero() -> None:
    rows = build_movement_summary_rows({MovementType.IN: (2, 8)})
    by_type = {r.type: (r.movement_count, r.total_quantity) for r in rows}
    assert by_type[MovementType.IN] == (2, 8)
    assert by_type[MovementType.OUT] == (0, 0)
    assert by_type[MovementType.ADJUSTMENT] == (0, 0)


def test_empty_gives_three_zeroed_rows() -> None:
    rows = build_movement_summary_rows({})
    assert len(rows) == 3
    assert all(r.movement_count == 0 and r.total_quantity == 0 for r in rows)
```

- [ ] **Step 2: Rodar — deve falhar**

TESTRUN `pytest tests/unit/test_report_logic.py -q`
Expected: FAIL (ImportError — `app.services.report` ainda não existe).

- [ ] **Step 3: Escrever o serviço**

`app/services/report.py`:
```python
"""Serviço de relatórios operacionais (read-only).

Orquestra agregações dos repositórios e monta os relatórios. O SQL fica nos
repositórios; aqui ficam composição e normalização.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_movement import MovementType
from app.repositories.movement import MovementRepository
from app.repositories.product import ProductRepository
from app.schemas.report import (
    InventoryValuationItem,
    InventoryValuationReport,
    InventoryValuationSummary,
    MovementsSummaryReport,
    MovementsSummaryRow,
)


def build_movement_summary_rows(
    counts: dict[MovementType, tuple[int, int]],
) -> list[MovementsSummaryRow]:
    """Uma linha por MovementType (ordem do enum), com zeros quando o tipo faltou."""
    return [
        MovementsSummaryRow(
            type=mtype,
            movement_count=counts.get(mtype, (0, 0))[0],
            total_quantity=counts.get(mtype, (0, 0))[1],
        )
        for mtype in MovementType
    ]


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def inventory_valuation(
        self, *, supplier_id: uuid.UUID | None = None, only_active: bool = True
    ) -> InventoryValuationReport:
        rows = await ProductRepository(self.session).inventory_valuation(
            supplier_id=supplier_id, only_active=only_active
        )
        items = [
            InventoryValuationItem(
                product_id=row.id,
                sku=row.sku,
                name=row.name,
                quantity=row.quantity,
                unit_price=row.unit_price,
                stock_value=row.stock_value,
            )
            for row in rows
        ]
        summary = InventoryValuationSummary(
            total_products=len(items),
            total_units=sum(i.quantity for i in items),
            total_value=sum((i.stock_value for i in items), Decimal("0.00")),
        )
        return InventoryValuationReport(
            generated_at=datetime.now(UTC), summary=summary, items=items
        )

    async def movements_summary(
        self,
        *,
        product_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> MovementsSummaryReport:
        raw = await MovementRepository(self.session).summary_by_type(
            product_id=product_id, date_from=date_from, date_to=date_to
        )
        counts = {row.type: (row.movement_count, row.total_quantity) for row in raw}
        rows = build_movement_summary_rows(counts)
        return MovementsSummaryReport(
            generated_at=datetime.now(UTC),
            date_from=date_from,
            date_to=date_to,
            rows=rows,
            total_movements=sum(r.movement_count for r in rows),
        )
```

- [ ] **Step 4: Rodar unit — deve passar**

TESTRUN `pytest tests/unit/test_report_logic.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**
```bash
git add app/services/report.py tests/unit/test_report_logic.py
git commit -m "feat(reports): ReportService + normalização do resumo (unit)"
```

---

## Task 5: Rotas — /reports

**Files:**
- Create: `app/api/v1/routes/reports.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Escrever as rotas**

`app/api/v1/routes/reports.py`:
```python
"""Rotas de relatórios operacionais (read-only, MANAGER+)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission
from app.dependencies.auth import require_permission
from app.dependencies.db import DBSession
from app.schemas.report import InventoryValuationReport, MovementsSummaryReport
from app.services.report import ReportService

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_permission(Permission.REPORT_READ))],
)


@router.get("/inventory-valuation", response_model=InventoryValuationReport)
async def inventory_valuation(
    session: DBSession,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    only_active: Annotated[bool, Query()] = True,
) -> InventoryValuationReport:
    return await ReportService(session).inventory_valuation(
        supplier_id=supplier_id, only_active=only_active
    )


@router.get("/movements-summary", response_model=MovementsSummaryReport)
async def movements_summary(
    session: DBSession,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> MovementsSummaryReport:
    return await ReportService(session).movements_summary(
        product_id=product_id, date_from=date_from, date_to=date_to
    )
```

- [ ] **Step 2: Registrar o router**

Em `app/api/v1/router.py`:
- adicionar `reports` ao import dos routes.
- `api_router.include_router(reports.router)`.

- [ ] **Step 3: Verificar boot**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**
```bash
git add app/api/v1/routes/reports.py app/api/v1/router.py
git commit -m "feat(reports): rotas GET /reports/inventory-valuation e /movements-summary"
```

---

## Task 6: Testes de integração

**Files:**
- Create: `tests/integration/test_reports.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_reports.py`:
```python
"""Integração: relatórios operacionais (valuation + resumo de movimentações)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _supplier(auth_client: AsyncClient) -> str:
    doc = str(uuid.uuid4().int)[:14]
    resp = await auth_client.post(f"{PREFIX}/suppliers", json={"name": "Forn", "document": doc})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _product(
    auth_client: AsyncClient, supplier_id: str, *, unit_price: str, active: bool = True
) -> str:
    sku = "R-" + uuid.uuid4().hex[:6]
    resp = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": sku, "name": "Prod", "supplier_id": supplier_id, "unit_price": unit_price},
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]
    if not active:
        patch = await auth_client.patch(f"{PREFIX}/products/{pid}", json={"is_active": False})
        assert patch.status_code == 200, patch.text
    return pid


async def _move(auth_client: AsyncClient, pid: str, mtype: str, qty: int) -> None:
    resp = await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": mtype, "quantity": qty}
    )
    assert resp.status_code == 201, resp.text


async def test_inventory_valuation(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    p1 = await _product(auth_client, sid, unit_price="10.00")
    p2 = await _product(auth_client, sid, unit_price="2.50")
    await _move(auth_client, p1, "in", 5)   # 5 * 10.00 = 50.00
    await _move(auth_client, p2, "in", 4)   # 4 *  2.50 = 10.00

    resp = await auth_client.get(f"{PREFIX}/reports/inventory-valuation")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"]["total_products"] == 2
    assert body["summary"]["total_units"] == 9
    assert float(body["summary"]["total_value"]) == 60.0
    # ordenado por stock_value desc -> p1 primeiro
    assert body["items"][0]["product_id"] == p1
    assert float(body["items"][0]["stock_value"]) == 50.0


async def test_valuation_only_active_filter(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    active = await _product(auth_client, sid, unit_price="10.00")
    inactive = await _product(auth_client, sid, unit_price="10.00", active=False)
    await _move(auth_client, active, "in", 1)

    default_ids = [
        i["product_id"] for i in (await auth_client.get(
            f"{PREFIX}/reports/inventory-valuation"
        )).json()["items"]
    ]
    assert active in default_ids and inactive not in default_ids

    all_ids = [
        i["product_id"] for i in (await auth_client.get(
            f"{PREFIX}/reports/inventory-valuation", params={"only_active": "false"}
        )).json()["items"]
    ]
    assert inactive in all_ids


async def test_valuation_supplier_filter(auth_client: AsyncClient) -> None:
    s1 = await _supplier(auth_client)
    s2 = await _supplier(auth_client)
    p1 = await _product(auth_client, s1, unit_price="10.00")
    await _product(auth_client, s2, unit_price="10.00")
    await _move(auth_client, p1, "in", 1)

    body = (await auth_client.get(
        f"{PREFIX}/reports/inventory-valuation", params={"supplier_id": s1}
    )).json()
    assert [i["product_id"] for i in body["items"]] == [p1]


async def test_movements_summary(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    pid = await _product(auth_client, sid, unit_price="1.00")
    await _move(auth_client, pid, "in", 10)
    await _move(auth_client, pid, "in", 5)
    await _move(auth_client, pid, "out", 3)

    body = (await auth_client.get(
        f"{PREFIX}/reports/movements-summary", params={"product_id": pid}
    )).json()
    by_type = {r["type"]: r for r in body["rows"]}
    assert by_type["in"]["movement_count"] == 2
    assert by_type["in"]["total_quantity"] == 15
    assert by_type["out"]["movement_count"] == 1
    assert by_type["out"]["total_quantity"] == 3
    assert by_type["adjustment"]["movement_count"] == 0
    assert by_type["adjustment"]["total_quantity"] == 0
    assert body["total_movements"] == 3


async def test_movements_summary_future_window_is_empty(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    pid = await _product(auth_client, sid, unit_price="1.00")
    await _move(auth_client, pid, "in", 10)

    body = (await auth_client.get(
        f"{PREFIX}/reports/movements-summary",
        params={"product_id": pid, "date_from": "2999-01-01T00:00:00Z"},
    )).json()
    assert body["total_movements"] == 0
    assert all(r["movement_count"] == 0 for r in body["rows"])


async def test_reports_require_auth(client: AsyncClient) -> None:
    assert (await client.get(f"{PREFIX}/reports/inventory-valuation")).status_code == 401
    assert (await client.get(f"{PREFIX}/reports/movements-summary")).status_code == 401
```

- [ ] **Step 2: Rodar — deve passar**

TESTRUN `pytest tests/integration/test_reports.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_reports.py
git commit -m "test(reports): integração de valuation e resumo de movimentações"
```

---

## Task 7: Verificação final + docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar README**

No `README.md`:
- na tabela de endpoints, adicionar (após `/dashboard/summary`):
```markdown
| GET | `/reports/inventory-valuation` | Valor de estoque por produto + totais | MANAGER+ |
| GET | `/reports/movements-summary` | Movimentações agregadas por tipo no período | MANAGER+ |
```
- na lista de permissões do RBAC (linha de funcionalidades), mencionar `report:read`.
- no roadmap, marcar relatórios:
```markdown
- [ ] **Fase 3**: ~~detecção de superestoque~~ ✅ · ~~relatórios~~ ✅ · export Excel · tarefas assíncronas
```

- [ ] **Step 2: Rodar todos os gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: ruff All checks passed, mypy Success, pytest todos verdes (anteriores + reports).

- [ ] **Step 3: Validar fluxo end-to-end (opcional, se Docker disponível)**

```bash
docker compose -f docker/docker-compose.yml up -d --build api
sleep 7
# token MANAGER -> GET /api/v1/reports/inventory-valuation e /movements-summary => 200
```

- [ ] **Step 4: Commit + push**
```bash
git add README.md
git commit -m "docs(reports): endpoints de relatórios + Fase 3 atualizada no README"
git push -u origin feat/operational-reports
```
Abrir PR pela URL retornada (ou via `gh pr create`, se disponível).

---

## Self-review

- **Cobertura do spec:** permissão report:read MANAGER+ (T1), agregações no repo
  (T2), schemas (T3), ReportService + lógica pura testada (T4), rotas /reports
  protegidas (T5), integração valuation+filtros+summary+auth (T6), gates+README
  (T7). ✔
- **Placeholders:** nenhum.
- **Consistência de tipos:** `Row[tuple[...]]` do repo (T2) consumido por
  atributo (`row.sku`, `row.stock_value`, `row.type`...) no serviço (T4);
  `MovementType` usado em repo/serviço/schema; `Decimal` em `unit_price`/
  `stock_value`/`total_value` ponta a ponta; `build_movement_summary_rows`
  (T4) casa com os unit tests (T4-step1) e com `summary_by_type` (T2).
- **Sem migration:** nenhuma alteração de schema do banco — relatórios leem
  tabelas existentes.
- **Notas:** valuation sem paginação (snapshot completo, por design — ver spec);
  `total_value` somado em `Decimal` com seed `Decimal("0.00")` para preservar a
  escala mesmo com lista vazia.
