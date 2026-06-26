# Detecção de Superestoque — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estender o sistema de alertas para detectar superestoque, via discriminador `kind` (LOW_STOCK/OVERSTOCK) no `StockAlert`, reusando serviço, rotas e permissões.

**Architecture:** `StockAlert` ganha `kind`; `min_stock_at_trigger` vira `threshold_at_trigger`. `AlertService.evaluate` avalia os dois tipos por chamada; dedup por `(produto, kind)`. Sem novas permissões. Migration 0003 com backfill.

**Tech Stack:** SQLAlchemy 2 async, Alembic, FastAPI, Pydantic v2, pytest. Segue os padrões das fases anteriores.

Spec: `docs/superpowers/specs/2026-06-26-deteccao-superestoque-design.md`.

---

## Convenção de testes (ambiente)

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

## Task 1: Modelo — AlertKind + kind + rename + índice

**Files:**
- Modify: `app/models/stock_alert.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Adicionar AlertKind e a coluna kind**

Em `app/models/stock_alert.py`:
- adicionar o enum (após `AlertStatus`):
```python
class AlertKind(StrEnum):
    LOW_STOCK = "low_stock"
    OVERSTOCK = "overstock"
```
- na classe `StockAlert`, adicionar a coluna `kind` logo após `status`:
```python
    kind: Mapped[AlertKind] = mapped_column(
        SAEnum(
            AlertKind,
            name="alert_kind",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AlertKind.LOW_STOCK,
        nullable=False,
    )
```

- [ ] **Step 2: Renomear min_stock_at_trigger → threshold_at_trigger**

Em `app/models/stock_alert.py`, trocar a linha:
```python
    min_stock_at_trigger: Mapped[int] = mapped_column(Integer, nullable=False)
```
por:
```python
    threshold_at_trigger: Mapped[int] = mapped_column(Integer, nullable=False)
```

- [ ] **Step 3: Atualizar o índice único parcial para incluir kind**

Em `app/models/stock_alert.py`, no `__table_args__`, trocar o `Index` por:
```python
        Index(
            "uq_stock_alerts_active_per_product",
            "product_id",
            "kind",
            unique=True,
            postgresql_where=text("status <> 'resolved'"),
        ),
```

- [ ] **Step 4: Exportar AlertKind**

Em `app/models/__init__.py`:
- trocar o import por:
```python
from app.models.stock_alert import ACTIVE_ALERT_STATUSES, AlertKind, AlertStatus, StockAlert
```
- adicionar `"AlertKind"` ao `__all__`.

- [ ] **Step 5: Verificar import**

TESTRUN `python -c "from app.models import AlertKind, StockAlert; print(AlertKind.OVERSTOCK.value)"`
Expected: `overstock`.

- [ ] **Step 6: Commit**
```bash
git add app/models/stock_alert.py app/models/__init__.py
git commit -m "feat(overstock): StockAlert.kind + threshold_at_trigger + índice por kind"
```

---

## Task 2: Migration 0003

**Files:**
- Create: `migrations/versions/0003_stock_alerts_overstock.py`

- [ ] **Step 1: Escrever a migration**

`migrations/versions/0003_stock_alerts_overstock.py`:
```python
"""stock alerts overstock (kind + threshold rename)

Revision ID: 0003_stock_alerts_overstock
Revises: 0002_stock_alerts
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_stock_alerts_overstock"
down_revision: str | None = "0002_stock_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    alert_kind = postgresql.ENUM("low_stock", "overstock", name="alert_kind")
    alert_kind.create(op.get_bind(), checkfirst=True)

    # add kind com default p/ backfill das linhas existentes; depois remove o default
    op.add_column(
        "stock_alerts",
        sa.Column(
            "kind",
            postgresql.ENUM("low_stock", "overstock", name="alert_kind", create_type=False),
            nullable=False,
            server_default="low_stock",
        ),
    )
    op.alter_column("stock_alerts", "kind", server_default=None)

    op.alter_column(
        "stock_alerts", "min_stock_at_trigger", new_column_name="threshold_at_trigger"
    )

    op.drop_index("uq_stock_alerts_active_per_product", table_name="stock_alerts")
    op.create_index(
        "uq_stock_alerts_active_per_product",
        "stock_alerts",
        ["product_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )


def downgrade() -> None:
    op.drop_index("uq_stock_alerts_active_per_product", table_name="stock_alerts")
    op.create_index(
        "uq_stock_alerts_active_per_product",
        "stock_alerts",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )
    op.alter_column(
        "stock_alerts", "threshold_at_trigger", new_column_name="min_stock_at_trigger"
    )
    op.drop_column("stock_alerts", "kind")
    op.execute("DROP TYPE IF EXISTS alert_kind")
```

- [ ] **Step 2: Aplicar a migration**

TESTRUN `alembic upgrade head`
Expected: log `Running upgrade 0002_stock_alerts -> 0003_stock_alerts_overstock`, sem erro.

- [ ] **Step 3: Commit**
```bash
git add migrations/versions/0003_stock_alerts_overstock.py
git commit -m "feat(overstock): migration 0003 (kind + rename + índice por kind)"
```

---

## Task 3: Repositório — filtro por kind

**Files:**
- Modify: `app/repositories/alert.py`

- [ ] **Step 1: get_active_for_product por kind**

Em `app/repositories/alert.py`:
- atualizar o import:
```python
from app.models.stock_alert import ACTIVE_ALERT_STATUSES, AlertKind, AlertStatus, StockAlert
```
- trocar `get_active_for_product` por:
```python
    async def get_active_for_product(
        self, product_id: uuid.UUID, kind: AlertKind
    ) -> StockAlert | None:
        """Retorna o alerta não-resolvido do produto para o tipo dado (dedup)."""
        stmt = (
            select(StockAlert)
            .where(StockAlert.product_id == product_id)
            .where(StockAlert.kind == kind)
            .where(StockAlert.status.in_(ACTIVE_ALERT_STATUSES))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

- [ ] **Step 2: filtro kind em list/count**

Em `app/repositories/alert.py`, no `_filtered_stmt`, adicionar o parâmetro e o filtro:
```python
    def _filtered_stmt(
        self,
        *,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        product_id: uuid.UUID | None = None,
    ) -> Select[tuple[StockAlert]]:
        stmt = select(StockAlert)
        if status is not None:
            stmt = stmt.where(StockAlert.status == status)
        if kind is not None:
            stmt = stmt.where(StockAlert.kind == kind)
        if product_id is not None:
            stmt = stmt.where(StockAlert.product_id == product_id)
        return stmt
```
E propagar `kind` em `list_filtered` e `count_filtered` (adicionar `kind: AlertKind | None = None`
na assinatura e passar `kind=kind` ao chamar `_filtered_stmt`):
```python
    async def list_filtered(
        self,
        *,
        offset: int,
        limit: int,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[StockAlert]:
        stmt = self._filtered_stmt(status=status, kind=kind, product_id=product_id)
        stmt = stmt.order_by(StockAlert.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        status: AlertStatus | None = None,
        kind: AlertKind | None = None,
        product_id: uuid.UUID | None = None,
    ) -> int:
        base = self._filtered_stmt(status=status, kind=kind, product_id=product_id).subquery()
        result = await self.session.execute(select(func.count()).select_from(base))
        return int(result.scalar_one())
```

- [ ] **Step 3: Verificar import**

TESTRUN `python -c "from app.repositories.alert import AlertRepository; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**
```bash
git add app/repositories/alert.py
git commit -m "feat(overstock): repo filtra alertas por kind"
```

---

## Task 4: Serviço — decide + evaluate generalizados

**Files:**
- Modify: `app/services/alert.py`
- Modify: `tests/unit/test_alert_logic.py`

- [ ] **Step 1: Atualizar os unit tests (nova assinatura)**

Substituir `tests/unit/test_alert_logic.py` por:
```python
"""Testes unitários da decisão de alerta (função pura)."""

from __future__ import annotations

import pytest

from app.services.alert import AlertAction, decide_alert_action

pytestmark = pytest.mark.unit


def test_opens_when_condition_and_no_active() -> None:
    assert decide_alert_action(condition_met=True, has_active=False) == AlertAction.OPEN


def test_noop_when_condition_but_already_active() -> None:
    assert decide_alert_action(condition_met=True, has_active=True) == AlertAction.NOOP


def test_resolves_when_condition_cleared_and_active() -> None:
    assert decide_alert_action(condition_met=False, has_active=True) == AlertAction.RESOLVE


def test_noop_when_healthy_and_no_active() -> None:
    assert decide_alert_action(condition_met=False, has_active=False) == AlertAction.NOOP
```

- [ ] **Step 2: Rodar — deve falhar**

TESTRUN `pytest tests/unit/test_alert_logic.py -q`
Expected: FAIL — `decide_alert_action` ainda usa a assinatura antiga (`quantity`/`min_stock`).

- [ ] **Step 3: Generalizar decide_alert_action**

Em `app/services/alert.py`, trocar a função `decide_alert_action` por:
```python
def decide_alert_action(*, condition_met: bool, has_active: bool) -> AlertAction:
    """Decide o que fazer com o alerta de um produto para um tipo.

    - condição presente e sem alerta ativo -> abrir
    - condição ausente e com alerta ativo -> resolver
    - caso contrário -> nada (idempotente)
    """
    if condition_met and not has_active:
        return AlertAction.OPEN
    if not condition_met and has_active:
        return AlertAction.RESOLVE
    return AlertAction.NOOP
```

- [ ] **Step 4: Generalizar evaluate (ambos os tipos)**

Em `app/services/alert.py`:
- atualizar o import dos models:
```python
from app.models.stock_alert import AlertKind, AlertStatus, StockAlert
```
- substituir o método `evaluate` inteiro por:
```python
    async def evaluate(self, product: Product) -> None:
        """Abre/resolve alertas de estoque baixo e superestoque do produto.

        Faz flush (não commit) — quem orquestra a transação commita.
        """
        checks: list[tuple[AlertKind, bool, int | None]] = [
            (AlertKind.LOW_STOCK, product.quantity <= product.min_stock, product.min_stock),
            (AlertKind.OVERSTOCK, product.is_overstock, product.max_stock),
        ]
        for kind, condition, threshold in checks:
            active = await self.repo.get_active_for_product(product.id, kind)
            action = decide_alert_action(condition_met=condition, has_active=active is not None)
            if action is AlertAction.OPEN:
                # condição verdadeira garante limite definido
                assert threshold is not None
                alert = StockAlert(
                    product_id=product.id,
                    kind=kind,
                    status=AlertStatus.OPEN,
                    triggered_quantity=product.quantity,
                    threshold_at_trigger=threshold,
                )
                try:
                    async with self.session.begin_nested():
                        self.session.add(alert)
                        await self.session.flush()
                except IntegrityError:
                    continue  # corrida: outro caminho abriu primeiro
                logger.info(
                    "alert_opened",
                    alert_id=str(alert.id),
                    product_id=str(product.id),
                    kind=kind.value,
                    quantity=product.quantity,
                    threshold=threshold,
                )
            elif action is AlertAction.RESOLVE and active is not None:
                active.status = AlertStatus.RESOLVED
                active.resolved_at = datetime.now(UTC)
                await self.session.flush()
                logger.info(
                    "alert_resolved",
                    alert_id=str(active.id),
                    product_id=str(product.id),
                    kind=kind.value,
                    quantity=product.quantity,
                )
```

- [ ] **Step 5: Rodar unit — deve passar**

TESTRUN `pytest tests/unit/test_alert_logic.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**
```bash
git add app/services/alert.py tests/unit/test_alert_logic.py
git commit -m "feat(overstock): evaluate avalia low + overstock; decide generalizado"
```

---

## Task 5: Schema — kind + threshold_at_trigger

**Files:**
- Modify: `app/schemas/alert.py`

- [ ] **Step 1: Atualizar AlertRead e AlertFilter**

Substituir `app/schemas/alert.py` por:
```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.stock_alert import AlertKind, AlertStatus


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    kind: AlertKind
    status: AlertStatus
    triggered_quantity: int
    threshold_at_trigger: int
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertFilter(BaseModel):
    """Filtros opcionais da listagem de alertas."""

    status: AlertStatus | None = None
    kind: AlertKind | None = None
    product_id: uuid.UUID | None = None
```

- [ ] **Step 2: Verificar import**

TESTRUN `python -c "from app.schemas.alert import AlertRead, AlertFilter; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/schemas/alert.py
git commit -m "feat(overstock): AlertRead/AlertFilter com kind + threshold_at_trigger"
```

---

## Task 6: Rota — filtro kind

**Files:**
- Modify: `app/api/v1/routes/alerts.py`

- [ ] **Step 1: Adicionar query param kind**

Em `app/api/v1/routes/alerts.py`:
- adicionar ao import dos models do alerta:
```python
from app.models.stock_alert import AlertKind, AlertStatus
```
- na rota `list_alerts`, adicionar o parâmetro `kind` e passá-lo ao filtro:
```python
@router.get("", response_model=Page[AlertRead])
async def list_alerts(
    session: DBSession,
    _: CurrentUser,
    pagination: Pagination,
    status: Annotated[AlertStatus | None, Query()] = None,
    kind: Annotated[AlertKind | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[AlertRead]:
    filters = AlertFilter(status=status, kind=kind, product_id=product_id)
    page = await AlertService(session).list(filters, pagination)
    return Page[AlertRead].create(
        [AlertRead.model_validate(a) for a in page.items], page.total, pagination
    )
```

- [ ] **Step 2: Verificar boot**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/api/v1/routes/alerts.py
git commit -m "feat(overstock): GET /alerts filtra por kind"
```

---

## Task 7: Testes de integração de superestoque

**Files:**
- Test: `tests/integration/test_overstock.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_overstock.py`:
```python
"""Integração: detecção de superestoque (alertas kind=overstock)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _make_product(auth_client: AsyncClient, *, min_stock: int, max_stock: int) -> str:
    sup = await auth_client.post(
        f"{PREFIX}/suppliers", json={"name": "Forn", "document": "11222333000181"}
    )
    sid = sup.json()["id"]
    prod = await auth_client.post(
        f"{PREFIX}/products",
        json={
            "sku": "OV-1",
            "name": "Produto Over",
            "supplier_id": sid,
            "min_stock": min_stock,
            "max_stock": max_stock,
        },
    )
    assert prod.status_code == 201, prod.text
    return prod.json()["id"]


async def test_overstock_opens_and_resolves(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=0, max_stock=10)

    # entra acima do máximo -> abre overstock
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 15}
    )
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["kind"] == "overstock"
    assert body["items"][0]["threshold_at_trigger"] == 10

    # sai voltando para <= máximo -> resolve
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "out", "quantity": 8}
    )
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid})
    statuses = [a["status"] for a in resp.json()["items"]]
    assert statuses == ["resolved"]


async def test_low_and_overstock_independent(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=5, max_stock=10)

    # vai a 15 -> overstock aberto, sem low
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 15}
    )
    over = await auth_client.get(f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid})
    assert over.json()["total"] == 1
    low = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "low_stock", "status": "open", "product_id": pid}
    )
    assert low.json()["total"] == 0

    # cai a 2 (<=5) -> overstock resolve, low abre
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "out", "quantity": 13}
    )
    over_open = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "overstock", "status": "open", "product_id": pid}
    )
    assert over_open.json()["total"] == 0
    low_open = await auth_client.get(
        f"{PREFIX}/alerts", params={"kind": "low_stock", "status": "open", "product_id": pid}
    )
    assert low_open.json()["total"] == 1


async def test_no_overstock_without_max_stock(auth_client: AsyncClient) -> None:
    sup = await auth_client.post(
        f"{PREFIX}/suppliers", json={"name": "Forn", "document": "11222333000181"}
    )
    sid = sup.json()["id"]
    prod = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": "NOMAX", "name": "Sem max", "supplier_id": sid, "min_stock": 0},
    )
    pid = prod.json()["id"]
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 9999}
    )
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"kind": "overstock", "product_id": pid})
    assert resp.json()["total"] == 0
```

- [ ] **Step 2: Rodar — deve passar**

TESTRUN `pytest tests/integration/test_overstock.py tests/integration/test_alerts.py -q`
Expected: PASS (overstock + low-stock existentes verdes).

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_overstock.py
git commit -m "test(overstock): integração de superestoque + independência low/over"
```

---

## Task 8: Verificação final + docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar README**

No `README.md`:
- na linha do endpoint `/alerts`, mencionar o filtro `kind`:
```markdown
| GET | `/alerts` | Alertas de estoque (filtro `status`, `kind`, `product_id`) | autenticado |
```
- no roadmap, iniciar a Fase 3:
```markdown
- [ ] **Fase 3**: ~~detecção de superestoque~~ ✅ · relatórios · export Excel · tarefas assíncronas
```

- [ ] **Step 2: Rodar todos os gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: ruff All checks passed, mypy Success, pytest todos verdes (44 anteriores + overstock).

- [ ] **Step 3: Validar migration + fluxo end-to-end**

```bash
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
docker compose -f docker/docker-compose.yml up -d --build api
sleep 7
docker compose -f docker/docker-compose.yml logs api | grep "0003_stock_alerts_overstock"
```
Expected: log mostra upgrade até `0003_stock_alerts_overstock`.

- [ ] **Step 4: Commit + push**
```bash
git add README.md
git commit -m "docs(overstock): filtro kind + Fase 3 iniciada no README"
git push -u origin feat/overstock-detection
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** AlertKind+kind+rename+índice (T1), migration 0003 c/ backfill
  (T2), repo filtra por kind (T3), decide+evaluate generalizados p/ ambos os tipos
  (T4), schema kind+threshold (T5), rota filtro kind (T6), integração overstock +
  independência + sem-max (T7), gates+README+migration e2e (T8). ✔
- **Placeholders:** nenhum.
- **Consistência de tipos:** `AlertKind` (T1) usado em repo (T3), serviço (T4),
  schema (T5), rota (T6); `get_active_for_product(product_id, kind)` (T3) usado no
  evaluate (T4); `threshold_at_trigger` consistente em modelo/migration/serviço/schema;
  `decide_alert_action(condition_met, has_active)` (T4) casa com os unit tests (T4-step1). ✔
- **Nota:** índice único agora `(product_id, kind)` — permite 1 low + 1 overstock
  ativos simultâneos no mesmo produto (impossível na prática, mas o modelo não os
  bloqueia mutuamente; tudo bem).
