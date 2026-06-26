# Export Excel dos Relatórios — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar download `.xlsx` (openpyxl) dos dois relatórios existentes via
endpoints `/export` dedicados, reusando o `ReportService` e a permissão
`report:read`. Serialização isolada em `app/utils/excel.py` (pura, testável).

**Architecture:** rota → `ReportService` (dados) → builder em `app/utils/excel.py`
(`Workbook`) → `workbook_to_bytes` → `fastapi.Response` com headers de download.
Sem migration, sem nova regra de negócio.

**Tech Stack:** FastAPI, openpyxl, Pydantic v2, pytest. Segue os padrões das
iterações anteriores.

Spec: `docs/superpowers/specs/2026-06-26-export-excel-design.md`.

---

## Convenção de testes (ambiente)

Mesma das iterações anteriores (Postgres real via Docker para integração;
`TEST_DATABASE_URL`). Unit de export **não** precisa de DB. Ver o plano dos
Relatórios para o atalho TESTRUN.

---

## Task 1: Dependência openpyxl

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Adicionar openpyxl (runtime) e types-openpyxl (dev)**

Em `pyproject.toml`:
- em `[project].dependencies`, adicionar:
```toml
    "openpyxl>=3.1.0",
```
- em `[project.optional-dependencies].dev`, adicionar:
```toml
    "types-openpyxl>=3.1.0",
```

- [ ] **Step 2: Instalar e verificar import**

Instalar no ambiente de dev e:
TESTRUN `python -c "import openpyxl; print(openpyxl.__version__)"`
Expected: imprime a versão.

- [ ] **Step 3: Commit**
```bash
git add pyproject.toml
git commit -m "build(export): adiciona openpyxl (+ types-openpyxl dev)"
```

---

## Task 2: Builder de planilhas + unit tests

**Files:**
- Create: `app/utils/excel.py`
- Create: `tests/unit/test_excel_export.py`

- [ ] **Step 1: Escrever os unit tests (devem falhar — módulo não existe)**

`tests/unit/test_excel_export.py`:
```python
"""Testes unitários da serialização Excel dos relatórios (sem DB)."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.stock_movement import MovementType
from app.schemas.report import (
    InventoryValuationItem,
    InventoryValuationReport,
    InventoryValuationSummary,
    MovementsSummaryReport,
    MovementsSummaryRow,
)
from app.utils.excel import (
    inventory_valuation_workbook,
    movements_summary_workbook,
    workbook_to_bytes,
)
from openpyxl import load_workbook

pytestmark = pytest.mark.unit


def _valuation_report() -> InventoryValuationReport:
    items = [
        InventoryValuationItem(
            product_id=uuid.uuid4(),
            sku="A-1",
            name="Produto A",
            quantity=5,
            unit_price=Decimal("10.00"),
            stock_value=Decimal("50.00"),
        ),
    ]
    return InventoryValuationReport(
        generated_at=datetime(2026, 6, 26, tzinfo=UTC),
        summary=InventoryValuationSummary(
            total_products=1, total_units=5, total_value=Decimal("50.00")
        ),
        items=items,
    )


def _movements_report() -> MovementsSummaryReport:
    rows = [
        MovementsSummaryRow(type=MovementType.IN, movement_count=2, total_quantity=15),
        MovementsSummaryRow(type=MovementType.OUT, movement_count=1, total_quantity=3),
        MovementsSummaryRow(type=MovementType.ADJUSTMENT, movement_count=0, total_quantity=0),
    ]
    return MovementsSummaryReport(
        generated_at=datetime(2026, 6, 26, tzinfo=UTC),
        date_from=None,
        date_to=None,
        rows=rows,
        total_movements=3,
    )


def _cells_text(ws) -> list[object]:
    return [c.value for row in ws.iter_rows() for c in row]


def test_valuation_workbook_has_item_and_totals() -> None:
    wb = inventory_valuation_workbook(_valuation_report())
    ws = wb.active
    values = _cells_text(ws)
    assert "SKU" in values
    assert "A-1" in values
    assert "Produto A" in values
    # valor do item e total presentes (numéricos)
    numeric = [v for v in values if isinstance(v, (int, float))]
    assert 50.0 in numeric  # stock_value do item / total_value


def test_movements_workbook_has_three_type_rows() -> None:
    wb = movements_summary_workbook(_movements_report())
    ws = wb.active
    values = [str(v) for v in _cells_text(ws) if v is not None]
    assert "in" in values and "out" in values and "adjustment" in values


def test_workbook_to_bytes_roundtrips() -> None:
    wb = inventory_valuation_workbook(_valuation_report())
    data = workbook_to_bytes(wb)
    assert isinstance(data, bytes) and len(data) > 0
    reopened = load_workbook(io.BytesIO(data))
    assert "Valuation" in reopened.sheetnames
```

- [ ] **Step 2: Rodar — deve falhar**

TESTRUN `pytest tests/unit/test_excel_export.py -q`
Expected: FAIL (ImportError — `app.utils.excel` não existe).

- [ ] **Step 3: Escrever o builder**

`app/utils/excel.py`:
```python
"""Serialização dos relatórios em planilhas Excel (.xlsx) com openpyxl.

Funções puras: recebem o schema do relatório e devolvem um Workbook. A rota
HTTP cuida do streaming/headers. Mantém a serialização testável sem DB.
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from app.schemas.report import InventoryValuationReport, MovementsSummaryReport

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MONEY_FORMAT = "#,##0.00"
_BOLD = Font(bold=True)


def _active_sheet(workbook: Workbook, title: str) -> Worksheet:
    ws = workbook.active
    if not isinstance(ws, Worksheet):  # pragma: no cover - Workbook() sempre cria a aba
        ws = workbook.create_sheet()
    ws.title = title
    return ws


def inventory_valuation_workbook(report: InventoryValuationReport) -> Workbook:
    wb = Workbook()
    ws = _active_sheet(wb, "Valuation")

    ws["A1"] = "Relatório de Valuation de Estoque"
    ws["A1"].font = _BOLD
    ws["A2"] = f"Gerado em: {report.generated_at.isoformat()}"

    header_row = 4
    headers = ["SKU", "Produto", "Quantidade", "Preço unitário", "Valor em estoque"]
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=title)
        cell.font = _BOLD

    row = header_row + 1
    for item in report.items:
        ws.cell(row=row, column=1, value=item.sku)
        ws.cell(row=row, column=2, value=item.name)
        ws.cell(row=row, column=3, value=item.quantity)
        price = ws.cell(row=row, column=4, value=item.unit_price)
        price.number_format = _MONEY_FORMAT
        value = ws.cell(row=row, column=5, value=item.stock_value)
        value.number_format = _MONEY_FORMAT
        row += 1

    row += 1  # linha em branco antes dos totais
    ws.cell(row=row, column=1, value="Total de produtos").font = _BOLD
    ws.cell(row=row, column=2, value=report.summary.total_products)
    row += 1
    ws.cell(row=row, column=1, value="Total de unidades").font = _BOLD
    ws.cell(row=row, column=2, value=report.summary.total_units)
    row += 1
    ws.cell(row=row, column=1, value="Valor total em estoque").font = _BOLD
    total = ws.cell(row=row, column=2, value=report.summary.total_value)
    total.number_format = _MONEY_FORMAT
    return wb


def movements_summary_workbook(report: MovementsSummaryReport) -> Workbook:
    wb = Workbook()
    ws = _active_sheet(wb, "Movimentações")

    ws["A1"] = "Relatório de Movimentações (resumo)"
    ws["A1"].font = _BOLD
    period_from = report.date_from.isoformat() if report.date_from else "início"
    period_to = report.date_to.isoformat() if report.date_to else "agora"
    ws["A2"] = f"Período: {period_from} → {period_to}"
    ws["A3"] = f"Gerado em: {report.generated_at.isoformat()}"

    header_row = 5
    headers = ["Tipo", "Qtd. de movimentações", "Quantidade total"]
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=title)
        cell.font = _BOLD

    row = header_row + 1
    for r in report.rows:
        ws.cell(row=row, column=1, value=r.type.value)
        ws.cell(row=row, column=2, value=r.movement_count)
        ws.cell(row=row, column=3, value=r.total_quantity)
        row += 1

    ws.cell(row=row, column=1, value="Total").font = _BOLD
    ws.cell(row=row, column=2, value=report.total_movements)
    return wb


def workbook_to_bytes(workbook: Workbook) -> bytes:
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 4: Rodar unit — deve passar**

TESTRUN `pytest tests/unit/test_excel_export.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**
```bash
git add app/utils/excel.py tests/unit/test_excel_export.py
git commit -m "feat(export): builders de planilha Excel dos relatórios (unit)"
```

---

## Task 3: Rotas de export

**Files:**
- Modify: `app/api/v1/routes/reports.py`

- [ ] **Step 1: Adicionar as duas rotas /export**

Em `app/api/v1/routes/reports.py`:
- ajustar imports:
```python
from fastapi import APIRouter, Depends, Query, Response

from app.utils.excel import (
    XLSX_MEDIA_TYPE,
    inventory_valuation_workbook,
    movements_summary_workbook,
    workbook_to_bytes,
)
```
- adicionar (após cada endpoint JSON correspondente):
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
    content = workbook_to_bytes(inventory_valuation_workbook(report))
    filename = f"inventory-valuation-{report.generated_at.date().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/movements-summary/export")
async def movements_summary_export(
    session: DBSession,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> Response:
    report = await ReportService(session).movements_summary(
        product_id=product_id, date_from=date_from, date_to=date_to
    )
    content = workbook_to_bytes(movements_summary_workbook(report))
    filename = f"movements-summary-{report.generated_at.date().isoformat()}.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: Verificar boot**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/api/v1/routes/reports.py
git commit -m "feat(export): rotas GET /reports/*/export (.xlsx)"
```

---

## Task 4: Testes de integração

**Files:**
- Create: `tests/integration/test_reports_export.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_reports_export.py`:
```python
"""Integração: export Excel dos relatórios."""

from __future__ import annotations

import io
import uuid

import pytest
from app.utils.excel import XLSX_MEDIA_TYPE
from httpx import AsyncClient
from openpyxl import load_workbook

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _supplier(auth_client: AsyncClient) -> str:
    doc = str(uuid.uuid4().int)[:14]
    resp = await auth_client.post(f"{PREFIX}/suppliers", json={"name": "Forn", "document": doc})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _product(auth_client: AsyncClient, supplier_id: str, *, unit_price: str) -> str:
    sku = "X-" + uuid.uuid4().hex[:6]
    resp = await auth_client.post(
        f"{PREFIX}/products",
        json={"sku": sku, "name": "Prod", "supplier_id": supplier_id, "unit_price": unit_price},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _move(auth_client: AsyncClient, pid: str, mtype: str, qty: int) -> None:
    resp = await auth_client.post(
        f"{PREFIX}/movements", json={"product_id": pid, "type": mtype, "quantity": qty}
    )
    assert resp.status_code == 201, resp.text


async def test_inventory_valuation_export(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    pid = await _product(auth_client, sid, unit_price="10.00")
    await _move(auth_client, pid, "in", 5)

    resp = await auth_client.get(f"{PREFIX}/reports/inventory-valuation/export")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == XLSX_MEDIA_TYPE
    assert "attachment" in resp.headers["content-disposition"]
    assert ".xlsx" in resp.headers["content-disposition"]

    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["Valuation"]
    values = [c.value for row in ws.iter_rows() for c in row]
    assert 50.0 in [v for v in values if isinstance(v, (int, float))]


async def test_movements_summary_export(auth_client: AsyncClient) -> None:
    sid = await _supplier(auth_client)
    pid = await _product(auth_client, sid, unit_price="1.00")
    await _move(auth_client, pid, "in", 10)
    await _move(auth_client, pid, "out", 4)

    resp = await auth_client.get(
        f"{PREFIX}/reports/movements-summary/export", params={"product_id": pid}
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == XLSX_MEDIA_TYPE

    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb["Movimentações"]
    text = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert "in" in text and "out" in text and "adjustment" in text


async def test_export_requires_auth(client: AsyncClient) -> None:
    assert (await client.get(f"{PREFIX}/reports/inventory-valuation/export")).status_code == 401
    assert (await client.get(f"{PREFIX}/reports/movements-summary/export")).status_code == 401
```

- [ ] **Step 2: Rodar — deve passar**

TESTRUN `pytest tests/integration/test_reports_export.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_reports_export.py
git commit -m "test(export): integração do download .xlsx dos relatórios"
```

---

## Task 5: Verificação final + docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar README**

No `README.md`:
- na tabela de endpoints, adicionar após as linhas de `/reports`:
```markdown
| GET | `/reports/inventory-valuation/export` | Download do valuation em `.xlsx` | MANAGER+ |
| GET | `/reports/movements-summary/export` | Download do resumo de movimentações em `.xlsx` | MANAGER+ |
```
- no roadmap, marcar export Excel:
```markdown
- [ ] **Fase 3**: ~~detecção de superestoque~~ ✅ · ~~relatórios~~ ✅ · ~~export Excel~~ ✅ · tarefas assíncronas
```

- [ ] **Step 2: Rodar todos os gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: ruff All checks passed, mypy Success, pytest todos verdes.

- [ ] **Step 3: Commit + push**
```bash
git add README.md
git commit -m "docs(export): endpoints de export .xlsx + Fase 3 atualizada"
git push -u origin feat/excel-export
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** dependência openpyxl (T1), builders puros + unit
  roundtrip (T2), rotas /export reusando ReportService (T3), integração com
  load_workbook + headers + auth (T4), gates+README (T5). ✔
- **Placeholders:** nenhum.
- **Consistência de tipos:** `Workbook` retornado pelos builders (T2) consumido
  por `workbook_to_bytes` (T2) e pelas rotas (T3); `XLSX_MEDIA_TYPE` compartilhado
  entre `app/utils/excel.py` e os testes; schemas de report reusados sem alteração.
- **Sem migration / sem nova permissão:** export é apresentação sobre dados
  existentes; reusa `report:read`.
- **Notas:** openpyxl grava `Decimal` como número (lido de volta como float nos
  testes — asserts usam float). `Workbook.active` tratado como possivelmente
  `None`/não-`Worksheet` em `_active_sheet` para satisfazer o mypy strict.
