# Tarefas Assíncronas (Export de Relatório) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduzir um worker **ARQ** (Redis) e o ciclo job → status → download
para gerar os exports `.xlsx` de forma assíncrona, reusando `ReportService` e os
builders de `app/utils/excel.py`. Resultado guardado no Redis com TTL (result
store nativo do ARQ). Sem migration.

**Architecture:** rota `export-async` enfileira via `ReportJobQueue` → worker ARQ
executa a task (gera relatório + `.xlsx`) e retorna o arquivo → ARQ persiste no
Redis → rotas de status/download leem pelo `job_id`. Toda interação com o ARQ fica
em `app/services/report_jobs.py` + `app/core/queue.py`.

**Tech Stack:** ARQ, FastAPI, SQLAlchemy 2 async, openpyxl, pytest.

Spec: `docs/superpowers/specs/2026-06-26-tarefas-assincronas-design.md`.

---

## Convenção de testes (ambiente)

Mesma das iterações anteriores (Postgres real para integração via Docker;
unit roda local sem I/O). A integração ARQ↔Redis real é validada no Docker; os
testes usam uma **fila fake** injetada.

---

## Task 1: Dependência ARQ + config TTL

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: arq em runtime**

Em `pyproject.toml`, `[project].dependencies`, adicionar:
```toml
    "arq>=0.26.0",
```

- [ ] **Step 2: TTL do resultado**

Em `app/core/config.py`, junto aos campos de aplicação:
```python
    REPORT_JOB_RESULT_TTL: int = 3600  # segundos que o resultado do job vive no Redis
```
Em `.env.example`, na seção Aplicação:
```
REPORT_JOB_RESULT_TTL=3600
```

- [ ] **Step 3: Instalar e verificar import**

Instalar no dev e:
TESTRUN `python -c "import arq; from arq.jobs import JobStatus; print('arq ok')"`
Expected: `arq ok`.

- [ ] **Step 4: Commit**
```bash
git add pyproject.toml app/core/config.py .env.example
git commit -m "build(async): adiciona arq + REPORT_JOB_RESULT_TTL"
```

---

## Task 2: ExportFile + helpers em excel.py (DRY) + unit

**Files:**
- Modify: `app/utils/excel.py`
- Modify: `app/api/v1/routes/reports.py`
- Create: `tests/unit/test_export_file.py`

- [ ] **Step 1: ExportFile + helpers**

Em `app/utils/excel.py`:
- ajustar imports do topo:
```python
import io
from dataclasses import dataclass
```
- adicionar após `XLSX_MEDIA_TYPE`:
```python
@dataclass(frozen=True)
class ExportFile:
    filename: str
    media_type: str
    content: bytes
```
- ao final do arquivo, adicionar:
```python
def inventory_valuation_export_file(report: InventoryValuationReport) -> ExportFile:
    content = workbook_to_bytes(inventory_valuation_workbook(report))
    filename = f"inventory-valuation-{report.generated_at.date().isoformat()}.xlsx"
    return ExportFile(filename=filename, media_type=XLSX_MEDIA_TYPE, content=content)


def movements_summary_export_file(report: MovementsSummaryReport) -> ExportFile:
    content = workbook_to_bytes(movements_summary_workbook(report))
    filename = f"movements-summary-{report.generated_at.date().isoformat()}.xlsx"
    return ExportFile(filename=filename, media_type=XLSX_MEDIA_TYPE, content=content)
```

- [ ] **Step 2: Rotas síncronas passam a usar os helpers**

Em `app/api/v1/routes/reports.py`, ajustar o import de excel para incluir os
helpers e `ExportFile`, e simplificar os dois endpoints `/export` síncronos:
```python
@router.get("/inventory-valuation/export")
async def inventory_valuation_export(
    session: DBSession,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    only_active: Annotated[bool, Query()] = True,
) -> Response:
    report = await ReportService(session).inventory_valuation(
        supplier_id=supplier_id, only_active=only_active
    )
    return _xlsx_response(inventory_valuation_export_file(report))
```
Adicionar um helper local no módulo de rotas (após os imports):
```python
def _xlsx_response(export: ExportFile) -> Response:
    return Response(
        content=export.content,
        media_type=export.media_type,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )
```
Fazer o mesmo no endpoint `movements-summary/export` (usar
`movements_summary_export_file` + `_xlsx_response`). Remover os imports agora não
usados (`XLSX_MEDIA_TYPE`, `inventory_valuation_workbook`, `movements_summary_workbook`,
`workbook_to_bytes`) deste arquivo de rotas.

- [ ] **Step 3: Unit test do helper**

`tests/unit/test_export_file.py`:
```python
"""Unit: helpers ExportFile (nome/medotype/bytes válidos)."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.schemas.report import (
    InventoryValuationItem,
    InventoryValuationReport,
    InventoryValuationSummary,
)
from app.utils.excel import XLSX_MEDIA_TYPE, inventory_valuation_export_file
from openpyxl import load_workbook

pytestmark = pytest.mark.unit


def _report() -> InventoryValuationReport:
    return InventoryValuationReport(
        generated_at=datetime(2026, 6, 26, tzinfo=UTC),
        summary=InventoryValuationSummary(
            total_products=1, total_units=5, total_value=Decimal("50.00")
        ),
        items=[
            InventoryValuationItem(
                product_id=uuid.uuid4(),
                sku="A-1",
                name="Produto A",
                quantity=5,
                unit_price=Decimal("10.00"),
                stock_value=Decimal("50.00"),
            )
        ],
    )


def test_export_file_fields_and_valid_xlsx() -> None:
    export = inventory_valuation_export_file(_report())
    assert export.filename == "inventory-valuation-2026-06-26.xlsx"
    assert export.media_type == XLSX_MEDIA_TYPE
    wb = load_workbook(io.BytesIO(export.content))
    assert "Valuation" in wb.sheetnames
```

- [ ] **Step 4: Rodar unit + verificar boot**

TESTRUN `pytest tests/unit/test_export_file.py tests/unit/test_excel_export.py -q`
Expected: PASS.
TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**
```bash
git add app/utils/excel.py app/api/v1/routes/reports.py tests/unit/test_export_file.py
git commit -m "refactor(export): ExportFile + helpers reutilizados pelas rotas síncronas"
```

---

## Task 3: Pool ARQ (app/core/queue.py)

**Files:**
- Create: `app/core/queue.py`

- [ ] **Step 1: Escrever o módulo**

`app/core/queue.py`:
```python
"""Pool de conexão ARQ (Redis) — singleton, espelha app/core/redis.py.

Usado pela API para enfileirar jobs e consultar resultados. O worker usa o
mesmo Redis (ver app/worker/settings.py).
"""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

_pool: ArqRedis | None = None


def report_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )


async def get_arq_pool() -> ArqRedis:
    """Retorna um pool ARQ singleton (criado de forma lazy)."""
    global _pool
    if _pool is None:
        _pool = await create_pool(report_redis_settings())
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
```

- [ ] **Step 2: Verificar import**

TESTRUN `python -c "from app.core.queue import get_arq_pool, report_redis_settings; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/core/queue.py
git commit -m "feat(async): pool ARQ singleton (core/queue)"
```

---

## Task 4: Worker ARQ (tasks + settings)

**Files:**
- Create: `app/worker/__init__.py`
- Create: `app/worker/tasks.py`
- Create: `app/worker/settings.py`

- [ ] **Step 1: __init__**

`app/worker/__init__.py`: vazio (pacote).

- [ ] **Step 2: tasks**

`app/worker/tasks.py`:
```python
"""Tasks ARQ: geração assíncrona dos exports de relatório.

A session factory vem do ctx (injetada no on_startup do worker), mantendo as
tasks desacopladas do engine global e testáveis com a sessão de teste.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.services.report import ReportService
from app.utils.excel import (
    ExportFile,
    inventory_valuation_export_file,
    movements_summary_export_file,
)


def _serialize(export: ExportFile) -> dict[str, Any]:
    return {"filename": export.filename, "media_type": export.media_type, "content": export.content}


async def generate_inventory_valuation_export(
    ctx: dict[str, Any],
    *,
    supplier_id: uuid.UUID | None = None,
    only_active: bool = True,
) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        report = await ReportService(session).inventory_valuation(
            supplier_id=supplier_id, only_active=only_active
        )
    return _serialize(inventory_valuation_export_file(report))


async def generate_movements_summary_export(
    ctx: dict[str, Any],
    *,
    product_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        report = await ReportService(session).movements_summary(
            product_id=product_id, date_from=date_from, date_to=date_to
        )
    return _serialize(movements_summary_export_file(report))
```

- [ ] **Step 3: settings**

`app/worker/settings.py`:
```python
"""Configuração do worker ARQ.

Executar: `arq app.worker.settings.WorkerSettings`.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.core.queue import report_redis_settings
from app.worker.tasks import (
    generate_inventory_valuation_export,
    generate_movements_summary_export,
)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["session_factory"] = async_session_factory


async def shutdown(ctx: dict[str, Any]) -> None:
    await engine.dispose()


class WorkerSettings:
    functions = [generate_inventory_valuation_export, generate_movements_summary_export]
    redis_settings = report_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    keep_result = settings.REPORT_JOB_RESULT_TTL
```

- [ ] **Step 4: Verificar import**

TESTRUN `python -c "from app.worker.settings import WorkerSettings; print([f.__name__ for f in WorkerSettings.functions])"`
Expected: lista com as duas tasks.

- [ ] **Step 5: Commit**
```bash
git add app/worker
git commit -m "feat(async): worker ARQ (tasks de export + WorkerSettings)"
```

---

## Task 5: Schemas + fila (report_jobs) + unit

**Files:**
- Create: `app/schemas/report_job.py`
- Create: `app/services/report_jobs.py`
- Create: `tests/unit/test_report_jobs.py`

- [ ] **Step 1: Schemas**

`app/schemas/report_job.py`:
```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ReportJobState(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    NOT_FOUND = "not_found"


class ReportJobAccepted(BaseModel):
    job_id: str
    status: ReportJobState


class ReportJobStatus(BaseModel):
    job_id: str
    status: ReportJobState
```

- [ ] **Step 2: Fila + mapeamento de status**

`app/services/report_jobs.py`:
```python
"""Abstração da fila de jobs de relatório sobre o ARQ.

Encapsula enqueue/status/result para que rotas (e testes) não dependam do ARQ
diretamente. `map_job_status` é pura e testável.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus

from app.exceptions.domain import ConflictError
from app.schemas.report_job import ReportJobState
from app.utils.excel import ExportFile


def map_job_status(status: JobStatus, *, success: bool | None = None) -> ReportJobState:
    if status in (JobStatus.deferred, JobStatus.queued):
        return ReportJobState.QUEUED
    if status == JobStatus.in_progress:
        return ReportJobState.IN_PROGRESS
    if status == JobStatus.not_found:
        return ReportJobState.NOT_FOUND
    return ReportJobState.COMPLETE if success else ReportJobState.FAILED


class ReportJobQueue:
    def __init__(self, pool: ArqRedis) -> None:
        self.pool = pool

    async def _enqueue(self, function: str, **kwargs: object) -> str:
        job = await self.pool.enqueue_job(function, **kwargs)
        if job is None:
            raise ConflictError("Não foi possível enfileirar o relatório.")
        return job.job_id

    async def enqueue_inventory_valuation(
        self, *, supplier_id: uuid.UUID | None, only_active: bool
    ) -> str:
        return await self._enqueue(
            "generate_inventory_valuation_export",
            supplier_id=supplier_id,
            only_active=only_active,
        )

    async def enqueue_movements_summary(
        self,
        *,
        product_id: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> str:
        return await self._enqueue(
            "generate_movements_summary_export",
            product_id=product_id,
            date_from=date_from,
            date_to=date_to,
        )

    async def get_status(self, job_id: str) -> ReportJobState:
        job = Job(job_id, self.pool)
        status = await job.status()
        if status != JobStatus.complete:
            return map_job_status(status)
        info = await job.result_info()
        return map_job_status(status, success=bool(info and info.success))

    async def get_result(self, job_id: str) -> ExportFile | None:
        job = Job(job_id, self.pool)
        if await job.status() != JobStatus.complete:
            return None
        info = await job.result_info()
        if info is None or not info.success:
            return None
        data = info.result
        return ExportFile(
            filename=data["filename"], media_type=data["media_type"], content=data["content"]
        )
```

- [ ] **Step 3: Unit do mapeamento**

`tests/unit/test_report_jobs.py`:
```python
"""Unit: mapeamento de JobStatus do ARQ -> ReportJobState."""

from __future__ import annotations

import pytest
from app.schemas.report_job import ReportJobState
from app.services.report_jobs import map_job_status
from arq.jobs import JobStatus

pytestmark = pytest.mark.unit


def test_queued_states() -> None:
    assert map_job_status(JobStatus.deferred) == ReportJobState.QUEUED
    assert map_job_status(JobStatus.queued) == ReportJobState.QUEUED


def test_in_progress() -> None:
    assert map_job_status(JobStatus.in_progress) == ReportJobState.IN_PROGRESS


def test_not_found() -> None:
    assert map_job_status(JobStatus.not_found) == ReportJobState.NOT_FOUND


def test_complete_success_vs_failure() -> None:
    assert map_job_status(JobStatus.complete, success=True) == ReportJobState.COMPLETE
    assert map_job_status(JobStatus.complete, success=False) == ReportJobState.FAILED
```

- [ ] **Step 4: Rodar unit**

TESTRUN `pytest tests/unit/test_report_jobs.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**
```bash
git add app/schemas/report_job.py app/services/report_jobs.py tests/unit/test_report_jobs.py
git commit -m "feat(async): schemas de job + ReportJobQueue (map_job_status testado)"
```

---

## Task 6: Dependência + rotas async + shutdown

**Files:**
- Create: `app/dependencies/queue.py`
- Modify: `app/api/v1/routes/reports.py`
- Modify: `app/main.py`

- [ ] **Step 1: Dependência da fila**

`app/dependencies/queue.py`:
```python
"""Dependência da fila de jobs de relatório (ARQ)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.queue import get_arq_pool
from app.services.report_jobs import ReportJobQueue


async def get_report_queue() -> ReportJobQueue:
    return ReportJobQueue(await get_arq_pool())


ReportQueue = Annotated[ReportJobQueue, Depends(get_report_queue)]
```

- [ ] **Step 2: Rotas async**

Em `app/api/v1/routes/reports.py`:
- imports adicionais:
```python
from fastapi import status as http_status

from app.dependencies.queue import ReportQueue
from app.exceptions.domain import ConflictError, NotFoundError
from app.schemas.report_job import ReportJobAccepted, ReportJobState, ReportJobStatus
```
- endpoints (após os exports síncronos correspondentes):
```python
@router.post(
    "/inventory-valuation/export-async",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=ReportJobAccepted,
)
async def inventory_valuation_export_async(
    queue: ReportQueue,
    supplier_id: Annotated[uuid.UUID | None, Query()] = None,
    only_active: Annotated[bool, Query()] = True,
) -> ReportJobAccepted:
    job_id = await queue.enqueue_inventory_valuation(
        supplier_id=supplier_id, only_active=only_active
    )
    return ReportJobAccepted(job_id=job_id, status=ReportJobState.QUEUED)


@router.post(
    "/movements-summary/export-async",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=ReportJobAccepted,
)
async def movements_summary_export_async(
    queue: ReportQueue,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> ReportJobAccepted:
    job_id = await queue.enqueue_movements_summary(
        product_id=product_id, date_from=date_from, date_to=date_to
    )
    return ReportJobAccepted(job_id=job_id, status=ReportJobState.QUEUED)


@router.get("/jobs/{job_id}", response_model=ReportJobStatus)
async def report_job_status(job_id: str, queue: ReportQueue) -> ReportJobStatus:
    state = await queue.get_status(job_id)
    if state is ReportJobState.NOT_FOUND:
        raise NotFoundError("Job de relatório", job_id)
    return ReportJobStatus(job_id=job_id, status=state)


@router.get("/jobs/{job_id}/download")
async def report_job_download(job_id: str, queue: ReportQueue) -> Response:
    state = await queue.get_status(job_id)
    if state is ReportJobState.NOT_FOUND:
        raise NotFoundError("Job de relatório", job_id)
    if state is ReportJobState.FAILED:
        raise ConflictError(
            "A geração do relatório falhou.", details={"status": state.value}
        )
    if state is not ReportJobState.COMPLETE:
        raise ConflictError(
            "Relatório ainda em processamento.", details={"status": state.value}
        )
    export = await queue.get_result(job_id)
    if export is None:
        raise NotFoundError("Resultado do relatório", job_id)
    return _xlsx_response(export)
```

- [ ] **Step 3: Fechar o pool no shutdown**

Em `app/main.py`, no `lifespan`, após `await close_redis()`:
```python
    from app.core.queue import close_arq_pool

    await close_arq_pool()
```
(ou importar no topo, conforme estilo do arquivo.)

- [ ] **Step 4: Verificar boot + paths**

TESTRUN `python -c "from app.main import create_app; app=create_app(); ps=app.openapi()['paths']; print(sorted(p for p in ps if 'jobs' in p or 'export-async' in p))"`
Expected: as 4 rotas novas presentes.

- [ ] **Step 5: Commit**
```bash
git add app/dependencies/queue.py app/api/v1/routes/reports.py app/main.py
git commit -m "feat(async): rotas export-async + status/download de job"
```

---

## Task 7: Testes de integração

**Files:**
- Create: `tests/integration/test_async_export.py`

- [ ] **Step 1: Escrever os testes (task direta + endpoints com fila fake)**

`tests/integration/test_async_export.py`:
```python
"""Integração: export assíncrono — task direta + endpoints com fila fake."""

from __future__ import annotations

import io
import uuid

import pytest
from app.dependencies.queue import get_report_queue
from app.schemas.report_job import ReportJobState
from app.utils.excel import ExportFile
from app.worker.tasks import generate_inventory_valuation_export
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _supplier(auth_client: AsyncClient) -> str:
    doc = str(uuid.uuid4().int)[:14]
    resp = await auth_client.post(f"{PREFIX}/suppliers", json={"name": "Forn", "document": doc})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _product(auth_client: AsyncClient, supplier_id: str, *, unit_price: str) -> str:
    sku = "AS-" + uuid.uuid4().hex[:6]
    resp = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": sku, "name": "Prod", "supplier_id": supplier_id, "unit_price": unit_price},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _move(auth_client: AsyncClient, pid: str, qty: int) -> None:
    resp = await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": "in", "quantity": qty}
    )
    assert resp.status_code == 201, resp.text


async def test_task_generates_valid_xlsx(
    auth_client: AsyncClient, db_engine: AsyncEngine
) -> None:
    sid = await _supplier(auth_client)
    pid = await _product(auth_client, sid, unit_price="10.00")
    await _move(auth_client, pid, 5)

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    result = await generate_inventory_valuation_export(
        {"session_factory": factory}, only_active=True
    )
    assert result["filename"].endswith(".xlsx")
    wb = load_workbook(io.BytesIO(result["content"]))
    values = [c.value for row in wb["Valuation"].iter_rows() for c in row]
    assert 50.0 in [v for v in values if isinstance(v, int | float)]


class _FakeQueue:
    """Fila em memória: simula enqueue/status/result sem ARQ/Redis."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}

    async def enqueue_inventory_valuation(self, **_: object) -> str:
        jid = uuid.uuid4().hex
        self.jobs[jid] = {"state": ReportJobState.QUEUED, "export": None}
        return jid

    async def enqueue_movements_summary(self, **_: object) -> str:
        return await self.enqueue_inventory_valuation()

    async def get_status(self, job_id: str) -> ReportJobState:
        job = self.jobs.get(job_id)
        return job["state"] if job else ReportJobState.NOT_FOUND

    async def get_result(self, job_id: str) -> ExportFile | None:
        job = self.jobs.get(job_id)
        return job["export"] if job else None

    def complete(self, job_id: str) -> None:
        self.jobs[job_id]["state"] = ReportJobState.COMPLETE
        self.jobs[job_id]["export"] = ExportFile(
            filename="x.xlsx", media_type="application/octet-stream", content=b"PK-bytes"
        )


@pytest.fixture
def fake_queue(client: AsyncClient) -> _FakeQueue:
    fake = _FakeQueue()
    app = client._app  # type: ignore[attr-defined]
    app.dependency_overrides[get_report_queue] = lambda: fake
    return fake


async def test_enqueue_then_status_then_download(
    auth_client: AsyncClient, fake_queue: _FakeQueue
) -> None:
    accepted = await auth_client.post(f"{PREFIX}/reports/inventory-valuation/export-async")
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    assert accepted.json()["status"] == "queued"

    # enquanto enfileirado: status queued, download 409
    st = await auth_client.get(f"{PREFIX}/reports/jobs/{job_id}")
    assert st.json()["status"] == "queued"
    assert (await auth_client.get(f"{PREFIX}/reports/jobs/{job_id}/download")).status_code == 409

    # conclui -> download entrega bytes
    fake_queue.complete(job_id)
    st2 = await auth_client.get(f"{PREFIX}/reports/jobs/{job_id}")
    assert st2.json()["status"] == "complete"
    dl = await auth_client.get(f"{PREFIX}/reports/jobs/{job_id}/download")
    assert dl.status_code == 200
    assert dl.content == b"PK-bytes"


async def test_unknown_job_is_404(auth_client: AsyncClient, fake_queue: _FakeQueue) -> None:
    assert (await auth_client.get(f"{PREFIX}/reports/jobs/nope")).status_code == 404
    assert (
        await auth_client.get(f"{PREFIX}/reports/jobs/nope/download")
    ).status_code == 404


async def test_async_endpoints_require_auth(client: AsyncClient) -> None:
    assert (
        await client.post(f"{PREFIX}/reports/inventory-valuation/export-async")
    ).status_code == 401
    assert (await client.get(f"{PREFIX}/reports/jobs/x")).status_code == 401
```

- [ ] **Step 2: Rodar**

TESTRUN `pytest tests/integration/test_async_export.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_async_export.py
git commit -m "test(async): task direta + ciclo enqueue/status/download (fila fake)"
```

---

## Task 8: Docker worker + README + gates finais

**Files:**
- Modify: `docker/docker-compose.yml`
- Modify: `README.md`

- [ ] **Step 1: Serviço worker no compose**

Em `docker/docker-compose.yml`, adicionar (após o serviço `api`):
```yaml
  worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    env_file:
      - ../.env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    entrypoint: ["arq", "app.worker.settings.WorkerSettings"]
    restart: unless-stopped
```

- [ ] **Step 2: README**

- na tabela de endpoints, após as linhas de export síncrono:
```markdown
| POST | `/reports/inventory-valuation/export-async` | Enfileira geração do `.xlsx` (assíncrono) | MANAGER+ |
| POST | `/reports/movements-summary/export-async` | Enfileira geração do `.xlsx` (assíncrono) | MANAGER+ |
| GET | `/reports/jobs/{id}` | Status do job de relatório | MANAGER+ |
| GET | `/reports/jobs/{id}/download` | Baixa o `.xlsx` do job concluído | MANAGER+ |
```
- na Stack, acrescentar ARQ (worker async).
- no roadmap, fechar a Fase 3:
```markdown
- [x] **Fase 3**: detecção de superestoque · relatórios · export Excel · tarefas assíncronas (ARQ)
```
- (opcional) nota em "Como rodar" de que o `docker compose up` agora sobe também o `worker`.

- [ ] **Step 3: Gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: tudo verde.

- [ ] **Step 4: Validar no Docker (dev) — fim-a-fim**

```bash
docker compose -f docker/docker-compose.yml up -d --build
# logs do worker devem mostrar "Starting worker" e as 2 funções registradas
docker compose -f docker/docker-compose.yml logs worker | grep -i "starting worker\|generate_"
# via Swagger (token MANAGER): POST export-async -> job_id; GET /jobs/{id} -> complete; download -> xlsx
```

- [ ] **Step 5: Commit + push**
```bash
git add docker/docker-compose.yml README.md
git commit -m "docs(async): worker no compose + endpoints async + Fase 3 concluída"
git push -u origin feat/async-tasks
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** dep arq + TTL (T1), ExportFile/helpers + DRY nas rotas
  síncronas (T2), pool ARQ (T3), worker tasks+settings (T4), schemas + fila +
  map_job_status testado (T5), dependência + 4 rotas async + shutdown (T6),
  integração task-direta + ciclo com fila fake (T7), docker worker + README +
  gates (T8). ✔
- **Placeholders:** nenhum.
- **Consistência de tipos:** `ExportFile` produzido em `excel.py` (T2), retornado
  serializado pela task (T4), reidratado pela fila (T5) e servido pela rota (T6);
  `ReportJobState` compartilhado entre schema (T5), fila (T5) e rotas (T6);
  `session_factory` injetado no ctx (T4-settings) e consumido pelas tasks (T4) e
  pelo teste (T7); nomes de função no `enqueue_job` (T5) == `__name__` das tasks
  registradas (T4).
- **Sem migration / sem nova permissão:** result store é o do ARQ (Redis+TTL);
  auth reusa `report:read` do router.
- **Notas:** worker no compose sobrescreve o entrypoint (não roda migrations — a
  API migra). Testes de endpoint usam fila fake (sem broker real); integração
  ARQ↔Redis validada no Docker (T8-step4).
