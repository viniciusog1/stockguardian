# Alertas de Estoque Baixo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alertas de estoque baixo persistidos, gerados automaticamente quando o estoque cruza o mínimo, com ciclo OPEN→ACKNOWLEDGED→RESOLVED e auto-resolve.

**Architecture:** Nova entidade `StockAlert`. Um `AlertService.evaluate(product)` central é chamado por `MovementService` e `ProductService` (na mesma transação) após mutarem o estoque. Dedup garantida por índice único parcial no banco. Só log estruturado como "notificação".

**Tech Stack:** FastAPI, SQLAlchemy 2 async (asyncpg), Pydantic v2, Alembic, PostgreSQL, pytest. Segue exatamente os padrões da Fase 1 (Repository + Service Layer, exceções de domínio, `require_role`, `Page`).

Spec: `docs/superpowers/specs/2026-06-26-alertas-estoque-baixo-design.md`.

---

## Convenção de testes (ambiente)

Local é Python 3.12; app/testes rodam em container 3.13 contra Postgres real (igual Fase 1).

**Subir infra uma vez:**
```bash
cd /Users/viniciusoliveira/Documents/stockguardian
cp -n .env.example .env
docker compose -f docker/docker-compose.yml up -d db redis
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian -c "CREATE DATABASE stockguardian_test;" 2>/dev/null || true
```

**Rodar testes/lint/type (usar a cada passo "Run"):**
```bash
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
docker run --rm --network stockguardian_default -v "$PWD":/app -w /app \
  -e TEST_DATABASE_URL="postgresql+asyncpg://stockguardian:stockguardian@db:5432/stockguardian_test" \
  -e SECRET_KEY="ci-test-secret" \
  python:3.13-slim bash -c "pip install -q uv && uv pip install --system -q '.[dev]' && <CMD>"
```
Substitua `<CMD>` por `pytest ...`, `ruff check .`, ou `mypy app`. Atalho usado abaixo: **TESTRUN `<CMD>`**.

---

## Task 1: Modelo StockAlert + enum AlertStatus

**Files:**
- Create: `app/models/stock_alert.py`
- Modify: `app/models/__init__.py`

- [ ] **Step 1: Criar o modelo**

`app/models/stock_alert.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# Estados que contam como "alerta ativo" (não-resolvido).
ACTIVE_ALERT_STATUSES = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)


class StockAlert(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stock_alerts"
    __table_args__ = (
        # Dedup: no máximo 1 alerta não-resolvido por produto (imposto pelo banco).
        Index(
            "uq_stock_alerts_active_per_product",
            "product_id",
            unique=True,
            postgresql_where=(__import__("sqlalchemy").text("status <> 'resolved'")),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[AlertStatus] = mapped_column(
        SAEnum(
            AlertStatus,
            name="alert_status",
            native_enum=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=AlertStatus.OPEN,
        nullable=False,
    )
    triggered_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    min_stock_at_trigger: Mapped[int] = mapped_column(Integer, nullable=False)

    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    product: Mapped[Product] = relationship(back_populates="alerts")
    acknowledger: Mapped[User | None] = relationship(lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StockAlert {self.status} product={self.product_id}>"
```

> Nota: o `__import__("sqlalchemy").text(...)` é feio; substitua por um import normal `from sqlalchemy import text` no topo e use `postgresql_where=text("status <> 'resolved'")`. (Mantido inline aqui só para deixar a dependência explícita.)

- [ ] **Step 2: Usar import normal de `text`**

No topo de `app/models/stock_alert.py`, garanta `from sqlalchemy import DateTime, ForeignKey, Index, Integer, text` e troque o `postgresql_where` para `text("status <> 'resolved'")`.

- [ ] **Step 3: Adicionar relationship em Product**

Em `app/models/product.py`, dentro da classe `Product`, junto dos outros relationships, adicionar:
```python
    alerts: Mapped[list["StockAlert"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
```
E no bloco `if TYPE_CHECKING:` adicionar `from app.models.stock_alert import StockAlert`.

- [ ] **Step 4: Registrar no models/__init__.py**

Em `app/models/__init__.py` adicionar imports e `__all__`:
```python
from app.models.stock_alert import ACTIVE_ALERT_STATUSES, AlertStatus, StockAlert
```
Acrescentar `"StockAlert"`, `"AlertStatus"`, `"ACTIVE_ALERT_STATUSES"` ao `__all__`.

- [ ] **Step 5: Verificar import**

TESTRUN `python -c "import app.models; print(app.models.StockAlert.__tablename__)"`
Expected: imprime `stock_alerts` sem erro.

- [ ] **Step 6: Commit**
```bash
git add app/models/stock_alert.py app/models/product.py app/models/__init__.py
git commit -m "feat(alerts): modelo StockAlert + enum AlertStatus"
```

---

## Task 2: Migration 0002

**Files:**
- Create: `migrations/versions/0002_stock_alerts.py`

- [ ] **Step 1: Escrever a migration**

`migrations/versions/0002_stock_alerts.py`:
```python
"""stock alerts

Revision ID: 0002_stock_alerts
Revises: 0001_initial
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_stock_alerts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    alert_status = postgresql.ENUM("open", "acknowledged", "resolved", name="alert_status")
    alert_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "stock_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("open", "acknowledged", "resolved", name="alert_status", create_type=False),
            nullable=False,
        ),
        sa.Column("triggered_quantity", sa.Integer(), nullable=False),
        sa.Column("min_stock_at_trigger", sa.Integer(), nullable=False),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_alerts_product_id", "stock_alerts", ["product_id"])
    op.create_index(
        "uq_stock_alerts_active_per_product",
        "stock_alerts",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )


def downgrade() -> None:
    op.drop_table("stock_alerts")
    op.execute("DROP TYPE IF EXISTS alert_status")
```

- [ ] **Step 2: Aplicar a migration**

TESTRUN `alembic upgrade head`
Expected: log `Running upgrade 0001_initial -> 0002_stock_alerts`, sem erro.

- [ ] **Step 3: Commit**
```bash
git add migrations/versions/0002_stock_alerts.py
git commit -m "feat(alerts): migration 0002 (tabela + enum + índice parcial)"
```

---

## Task 3: Schemas de alerta

**Files:**
- Create: `app/schemas/alert.py`

- [ ] **Step 1: Escrever schemas**

`app/schemas/alert.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.stock_alert import AlertStatus


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    status: AlertStatus
    triggered_quantity: int
    min_stock_at_trigger: int
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AlertFilter(BaseModel):
    status: AlertStatus | None = None
    product_id: uuid.UUID | None = None
```

- [ ] **Step 2: Verificar import**

TESTRUN `python -c "from app.schemas.alert import AlertRead, AlertFilter; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/schemas/alert.py
git commit -m "feat(alerts): schemas AlertRead/AlertFilter"
```

---

## Task 4: AlertRepository

**Files:**
- Create: `app/repositories/alert.py`

- [ ] **Step 1: Escrever o repositório**

`app/repositories/alert.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select

from app.models.stock_alert import ACTIVE_ALERT_STATUSES, AlertStatus, StockAlert
from app.repositories.base import BaseRepository


class AlertRepository(BaseRepository[StockAlert]):
    model = StockAlert

    async def get_active_for_product(self, product_id: uuid.UUID) -> StockAlert | None:
        stmt = (
            select(StockAlert)
            .where(StockAlert.product_id == product_id)
            .where(StockAlert.status.in_(ACTIVE_ALERT_STATUSES))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _filtered_stmt(
        self,
        *,
        status: AlertStatus | None = None,
        product_id: uuid.UUID | None = None,
    ) -> Select[tuple[StockAlert]]:
        stmt = select(StockAlert)
        if status is not None:
            stmt = stmt.where(StockAlert.status == status)
        if product_id is not None:
            stmt = stmt.where(StockAlert.product_id == product_id)
        return stmt

    async def list_filtered(
        self,
        *,
        offset: int,
        limit: int,
        status: AlertStatus | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[StockAlert]:
        stmt = self._filtered_stmt(status=status, product_id=product_id)
        stmt = stmt.order_by(StockAlert.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        status: AlertStatus | None = None,
        product_id: uuid.UUID | None = None,
    ) -> int:
        base = self._filtered_stmt(status=status, product_id=product_id).subquery()
        result = await self.session.execute(select(func.count()).select_from(base))
        return int(result.scalar_one())
```

> `datetime` é importado para consistência com `movement.py`, mas se ruff acusar import não usado, remova-o.

- [ ] **Step 2: Verificar import**

TESTRUN `python -c "from app.repositories.alert import AlertRepository; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/repositories/alert.py
git commit -m "feat(alerts): AlertRepository"
```

---

## Task 5: Função de decisão pura + unit tests

**Files:**
- Create: `app/services/alert.py` (parcial — só a função pura nesta task)
- Test: `tests/unit/test_alert_logic.py`

- [ ] **Step 1: Escrever o teste falho**

`tests/unit/test_alert_logic.py`:
```python
"""Testes unitários da decisão de alerta (função pura)."""

from __future__ import annotations

import pytest

from app.services.alert import AlertAction, decide_alert_action

pytestmark = pytest.mark.unit


def test_opens_when_crossing_minimum_and_no_active() -> None:
    assert decide_alert_action(quantity=2, min_stock=5, has_active=False) == AlertAction.OPEN


def test_noop_when_low_but_already_active() -> None:
    assert decide_alert_action(quantity=2, min_stock=5, has_active=True) == AlertAction.NOOP


def test_resolves_when_recovered_and_active() -> None:
    assert decide_alert_action(quantity=9, min_stock=5, has_active=True) == AlertAction.RESOLVE


def test_noop_when_healthy_and_no_active() -> None:
    assert decide_alert_action(quantity=9, min_stock=5, has_active=False) == AlertAction.NOOP


def test_zero_min_and_zero_qty_opens() -> None:
    assert decide_alert_action(quantity=0, min_stock=0, has_active=False) == AlertAction.OPEN
```

- [ ] **Step 2: Rodar — deve falhar**

TESTRUN `pytest tests/unit/test_alert_logic.py -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError` (app.services.alert ainda não existe).

- [ ] **Step 3: Implementar a função pura**

Criar `app/services/alert.py` com (apenas isto por enquanto):
```python
"""Serviço de alertas de estoque baixo."""

from __future__ import annotations

from enum import StrEnum


class AlertAction(StrEnum):
    OPEN = "open"
    RESOLVE = "resolve"
    NOOP = "noop"


def decide_alert_action(*, quantity: int, min_stock: int, has_active: bool) -> AlertAction:
    """Decide o que fazer com o alerta de um produto.

    - estoque <= mínimo e sem alerta ativo -> abrir
    - estoque > mínimo e com alerta ativo -> resolver
    - caso contrário -> nada (idempotente)
    """
    is_low = quantity <= min_stock
    if is_low and not has_active:
        return AlertAction.OPEN
    if not is_low and has_active:
        return AlertAction.RESOLVE
    return AlertAction.NOOP
```

- [ ] **Step 4: Rodar — deve passar**

TESTRUN `pytest tests/unit/test_alert_logic.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**
```bash
git add app/services/alert.py tests/unit/test_alert_logic.py
git commit -m "feat(alerts): decide_alert_action + unit tests"
```

---

## Task 6: AlertService (orquestração)

**Files:**
- Modify: `app/services/alert.py`

- [ ] **Step 1: Adicionar a classe AlertService**

Acrescentar a `app/services/alert.py` (mantendo a função pura da Task 5):
```python
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.exceptions.domain import ConflictError, NotFoundError
from app.models.stock_alert import AlertStatus, StockAlert
from app.models.product import Product
from app.repositories.alert import AlertRepository
from app.schemas.alert import AlertFilter
from app.schemas.common import Page, PaginationParams

logger = get_logger(__name__)


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AlertRepository(session)

    async def evaluate(self, product: Product) -> StockAlert | None:
        """Abre ou resolve alerta conforme o estoque do produto.

        Faz flush (não commit) — quem orquestra a transação commita.
        """
        active = await self.repo.get_active_for_product(product.id)
        action = decide_alert_action(
            quantity=product.quantity,
            min_stock=product.min_stock,
            has_active=active is not None,
        )
        if action is AlertAction.OPEN:
            alert = StockAlert(
                product_id=product.id,
                status=AlertStatus.OPEN,
                triggered_quantity=product.quantity,
                min_stock_at_trigger=product.min_stock,
            )
            try:
                async with self.session.begin_nested():
                    self.session.add(alert)
                    await self.session.flush()
            except IntegrityError:
                # Corrida: outro caminho abriu o alerta primeiro. Idempotente.
                return None
            logger.info(
                "alert_opened",
                alert_id=str(alert.id),
                product_id=str(product.id),
                quantity=product.quantity,
                min_stock=product.min_stock,
            )
            return alert
        if action is AlertAction.RESOLVE and active is not None:
            active.status = AlertStatus.RESOLVED
            active.resolved_at = datetime.now(UTC)
            await self.session.flush()
            logger.info(
                "alert_resolved",
                alert_id=str(active.id),
                product_id=str(product.id),
                quantity=product.quantity,
            )
            return active
        return None

    async def get(self, alert_id: uuid.UUID) -> StockAlert:
        alert = await self.repo.get(alert_id)
        if alert is None:
            raise NotFoundError("Alerta", alert_id)
        return alert

    async def list(self, filters: AlertFilter, params: PaginationParams) -> Page[StockAlert]:
        kwargs = filters.model_dump(exclude_none=True)
        items = await self.repo.list_filtered(offset=params.offset, limit=params.limit, **kwargs)
        total = await self.repo.count_filtered(**kwargs)
        return Page.create(items, total, params)

    async def acknowledge(self, alert_id: uuid.UUID, user_id: uuid.UUID) -> StockAlert:
        alert = await self.get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise ConflictError("Alerta já resolvido não pode ser reconhecido.")
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def resolve(self, alert_id: uuid.UUID) -> StockAlert:
        alert = await self.get(alert_id)
        if alert.status is AlertStatus.RESOLVED:
            raise ConflictError("Alerta já está resolvido.")
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(alert)
        return alert
```

> Coloque os novos `import` no topo do arquivo (junto do `from enum import StrEnum`), não no meio.

- [ ] **Step 2: Verificar import + tipos**

TESTRUN `python -c "from app.services.alert import AlertService; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/services/alert.py
git commit -m "feat(alerts): AlertService (evaluate/acknowledge/resolve/list)"
```

---

## Task 7: Integrar no MovementService

**Files:**
- Modify: `app/services/movement.py`

- [ ] **Step 1: Chamar evaluate antes do commit**

Em `app/services/movement.py`, no método `create`, importar no topo:
```python
from app.services.alert import AlertService
```
E, dentro de `create`, **após** `await self.repo.add(movement)` e **antes** de `await self.session.commit()`, inserir:
```python
        await AlertService(self.session).evaluate(product)
```
(O `product` já está carregado com `for update` e com `quantity` atualizado.)

- [ ] **Step 2: Rodar a suíte existente (não pode regredir)**

TESTRUN `pytest tests/integration/test_stock_flow.py -q`
Expected: PASS (testes da Fase 1 continuam verdes).

- [ ] **Step 3: Commit**
```bash
git add app/services/movement.py
git commit -m "feat(alerts): avaliar alerta a cada movimentação"
```

---

## Task 8: Integrar no ProductService

**Files:**
- Modify: `app/services/product.py`

- [ ] **Step 1: Avaliar quando min_stock/quantity mudam**

Em `app/services/product.py`, importar no topo:
```python
from app.services.alert import AlertService
```
No método `update`, após aplicar o payload (`for field, value in payload.items(): setattr(...)`) e **antes** de `await self.session.commit()`, inserir:
```python
        if "min_stock" in payload or "quantity" in payload:
            await self.session.flush()  # garante product.quantity/min_stock atuais
            await AlertService(self.session).evaluate(product)
```

- [ ] **Step 2: Rodar a suíte existente**

TESTRUN `pytest tests/integration/test_stock_flow.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add app/services/product.py
git commit -m "feat(alerts): avaliar alerta ao alterar min_stock/quantity do produto"
```

---

## Task 9: Rotas da API

**Files:**
- Create: `app/api/v1/routes/alerts.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Escrever as rotas**

`app/api/v1/routes/alerts.py`:
```python
"""Rotas de alertas de estoque baixo."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import CurrentUser, require_role
from app.dependencies.db import DBSession
from app.models.stock_alert import AlertStatus
from app.models.user import UserRole
from app.schemas.alert import AlertFilter, AlertRead
from app.schemas.common import Page
from app.services.alert import AlertService
from app.utils.pagination import Pagination

router = APIRouter(prefix="/alerts", tags=["alerts"])

OperatorUp = Depends(require_role(UserRole.OPERATOR, UserRole.MANAGER))
ManagerUp = Depends(require_role(UserRole.MANAGER))


@router.get("", response_model=Page[AlertRead])
async def list_alerts(
    session: DBSession,
    _: CurrentUser,
    pagination: Pagination,
    status: Annotated[AlertStatus | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[AlertRead]:
    filters = AlertFilter(status=status, product_id=product_id)
    page = await AlertService(session).list(filters, pagination)
    return Page[AlertRead].create(
        [AlertRead.model_validate(a) for a in page.items], page.total, pagination
    )


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(alert_id: uuid.UUID, session: DBSession, _: CurrentUser) -> AlertRead:
    alert = await AlertService(session).get(alert_id)
    return AlertRead.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead, dependencies=[OperatorUp])
async def acknowledge_alert(
    alert_id: uuid.UUID, session: DBSession, current_user: CurrentUser
) -> AlertRead:
    alert = await AlertService(session).acknowledge(alert_id, current_user.id)
    return AlertRead.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertRead, dependencies=[ManagerUp])
async def resolve_alert(alert_id: uuid.UUID, session: DBSession) -> AlertRead:
    alert = await AlertService(session).resolve(alert_id)
    return AlertRead.model_validate(alert)
```

> `acknowledge_alert` precisa de `current_user` para gravar quem reconheceu; por isso usa `CurrentUser` no parâmetro além do `OperatorUp` em `dependencies`.

- [ ] **Step 2: Registrar o router**

Em `app/api/v1/router.py`, importar `alerts` e incluir:
```python
from app.api.v1.routes import alerts, auth, movements, products, suppliers, users
...
api_router.include_router(alerts.router)
```

- [ ] **Step 3: Verificar boot**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**
```bash
git add app/api/v1/routes/alerts.py app/api/v1/router.py
git commit -m "feat(alerts): rotas /alerts (list/get/acknowledge/resolve)"
```

---

## Task 10: Testes de integração

**Files:**
- Test: `tests/integration/test_alerts.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_alerts.py`:
```python
"""Integração: ciclo de vida dos alertas de estoque baixo."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _make_product(auth_client: AsyncClient, *, min_stock: int = 10) -> str:
    sup = await auth_client.post(
        f"{PREFIX}/suppliers", json={"name": "Forn", "document": "11222333000181"}
    )
    sid = sup.json()["id"]
    prod = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": "AL-1", "name": "Produto Alerta", "supplier_id": sid, "min_stock": min_stock},
    )
    assert prod.status_code == 201, prod.text
    return prod.json()["id"]


async def test_out_below_minimum_opens_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 8}
    )  # 8 <= 10 já abre
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"status": "open"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["product_id"] == pid
    assert body["items"][0]["triggered_quantity"] == 8


async def test_recover_stock_resolves_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )  # abre
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 20}
    )  # 25 > 10 -> resolve
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid})
    statuses = [a["status"] for a in resp.json()["items"]]
    assert statuses == ["resolved"]


async def test_no_duplicate_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "out", "quantity": 2}
    )  # ainda baixo, não duplica
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid})
    assert resp.json()["total"] == 1


async def test_raising_min_stock_opens_alert(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=1)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )  # 5 > 1, sem alerta
    assert (await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid})).json()["total"] == 0
    await auth_client.patch(f"{PREFIX}/products/{pid}", json={"min_stock": 10})  # 5 <= 10 -> abre
    resp = await auth_client.get(f"{PREFIX}/alerts", params={"product_id": pid, "status": "open"})
    assert resp.json()["total"] == 1


async def test_acknowledge_and_resolve(auth_client: AsyncClient) -> None:
    pid = await _make_product(auth_client, min_stock=10)
    await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": 5}
    )
    alert_id = (await auth_client.get(f"{PREFIX}/alerts")).json()["items"][0]["id"]

    ack = await auth_client.post(f"{PREFIX}/alerts/{alert_id}/acknowledge")
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"
    assert ack.json()["acknowledged_by"] is not None

    res = await auth_client.post(f"{PREFIX}/alerts/{alert_id}/resolve")
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"

    # resolver de novo -> conflito
    again = await auth_client.post(f"{PREFIX}/alerts/{alert_id}/resolve")
    assert again.status_code == 409
```

- [ ] **Step 2: Rodar — deve passar**

TESTRUN `pytest tests/integration/test_alerts.py -q`
Expected: PASS (5 passed).

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_alerts.py
git commit -m "test(alerts): integração do ciclo de vida"
```

---

## Task 11: Verificação final + docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar README**

Em `README.md`: adicionar linha de endpoints `/alerts` na tabela e marcar parte da Fase 2 no roadmap:
```markdown
| GET | `/alerts` | Alertas de estoque baixo (filtro `status`, `product_id`) | autenticado |
| POST | `/alerts/{id}/acknowledge` | Reconhecer alerta | OPERATOR+ |
| POST | `/alerts/{id}/resolve` | Resolver alerta | MANAGER+ |
```
E no roadmap, sob Fase 2: `- [x] Alertas de estoque baixo`.

- [ ] **Step 2: Rodar todos os gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: ruff All checks passed, mypy Success, pytest todos verdes (Fase 1 + alertas).

- [ ] **Step 3: Subir stack e validar migration end-to-end**

```bash
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
docker compose -f docker/docker-compose.yml up -d --build api
sleep 7
docker compose -f docker/docker-compose.yml logs api | grep "0002_stock_alerts"
curl -s -w "\n%{http_code}\n" http://localhost:8000/health
```
Expected: log mostra upgrade até `0002_stock_alerts`; health 200.

- [ ] **Step 4: Commit + push**
```bash
git add README.md
git commit -m "docs(alerts): endpoints + roadmap Fase 2"
git push
```

---

## Self-review (preenchido pelo autor do plano)

- **Cobertura do spec:** modelo+enum (T1), migration+índice parcial (T2), schemas (T3), repo (T4), decisão pura (T5), AlertService evaluate/ack/resolve/list (T6), integração movement (T7) e product/min_stock (T8), API+permissões (T9), testes unit+integração (T10), gates+migration e2e (T11). ✔
- **Placeholders:** nenhum — todo passo tem código/comando concreto.
- **Consistência de tipos:** `decide_alert_action`/`AlertAction` (T5) usados em T6; `AlertRepository.get_active_for_product/list_filtered/count_filtered` (T4) usados em T6; `AlertService.evaluate/get/list/acknowledge/resolve` (T6) usados em T7/T8/T9; `AlertRead`/`AlertFilter` (T3) usados em T9/T10. ✔
- **Nota de risco:** `begin_nested()` exige que a sessão suporte SAVEPOINT (Postgres ✔). O caminho sequencial de dedup é coberto por `get_active_for_product`; o `IntegrityError` cobre só corrida concorrente.
