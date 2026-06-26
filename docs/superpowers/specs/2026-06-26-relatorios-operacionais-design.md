# Design — Relatórios Operacionais (Fase 3, iteração 2)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

A Fase 2 entregou um **dashboard** com contadores gerais e deixou explicitamente
fora de escopo (para iterações futuras): valor total de estoque, saúde do estoque
e movimentações por janela temporal. A Fase 3 retoma esses pontos como
**relatórios operacionais** — endpoints analíticos read-only que produzem dados
tabulares com totalizadores.

Esses relatórios são também a base para a próxima iteração da Fase 3 (**export
Excel**): por isso o formato de saída é deliberadamente linha-a-linha + resumo,
fácil de serializar para `.xlsx` depois.

Independe do trabalho de alertas/superestoque (usa entidades já existentes:
`Product`, `StockMovement`), portanto a branch parte de `main`.

## Escopo desta iteração

Dois relatórios, ambos sob o prefixo `/reports`:

1. **Valuation de estoque** (`GET /reports/inventory-valuation`) — valor financeiro
   parado em estoque, por produto + totais. Responde "quanto de capital está em
   estoque?".
2. **Resumo de movimentações** (`GET /reports/movements-summary`) — agregados de
   movimentação por tipo (`in`/`out`/`adjustment`) num período. Responde "o que
   entrou/saiu/foi ajustado neste período?".

## Decisões fechadas

- **Acesso:** nova permissão nomeada `report:read` (RBAC granular da Fase 2),
  concedida a **MANAGER+** (mesmo nível do dashboard). ADMIN herda todas.
- **Camadas:** `ReportService` (read-only) orquestra; o SQL de agregação fica nos
  **repositórios** (`ProductRepository`, `MovementRepository`), respeitando a
  regra "só o repo emite SQL".
- **Sem cache** nesta iteração — relatórios são parametrizados (filtros/período) e
  menos "quentes" que o dashboard; cache/materialização fica para a iteração de
  tarefas assíncronas.
- **Sem paginação** no valuation — o relatório é um snapshot completo do estoque
  (necessário para o export Excel somar tudo); é limitado pelos filtros
  (`supplier_id`, `only_active`). Aceitável no escopo de portfólio; anotado como
  ponto a revisitar se o catálogo crescer.
- **Dinheiro como `Decimal`** — `unit_price` é `Numeric(12,2)`; `stock_value =
  quantity * unit_price` é calculado **no SQL** (retorna `Decimal`), evitando
  divergência float. Os schemas Pydantic expõem `Decimal`.
- **`generated_at`** (UTC) em cada relatório — carimbo de quando foi gerado, útil
  no export e para o cliente.

## Relatório 1 — Valuation de estoque

### Query (no `ProductRepository`)

```sql
SELECT p.id, p.sku, p.name, p.quantity, p.unit_price,
       (p.quantity * p.unit_price) AS stock_value
FROM products p
WHERE (:only_active IS FALSE OR p.is_active = TRUE)
  AND (:supplier_id IS NULL OR p.supplier_id = :supplier_id)
ORDER BY stock_value DESC, p.sku ASC
```

- Novo método `ProductRepository.inventory_valuation(*, supplier_id, only_active)`
  → `Sequence[Row[...]]` (colunas tipadas: `uuid`, `str`, `str`, `int`, `Decimal`,
  `Decimal`).
- O **resumo** (`total_products`, `total_units`, `total_value`) é computado no
  serviço a partir das linhas já carregadas (uma única query; sem risco de
  inconsistência entre linhas e total).

### Saída

```python
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
```

### Endpoint

`GET /reports/inventory-valuation?supplier_id=&only_active=true`
- `only_active: bool = True` (default só produtos ativos).
- `supplier_id: uuid.UUID | None = None`.
- Acesso `report:read`.

## Relatório 2 — Resumo de movimentações

### Query (no `MovementRepository`)

```sql
SELECT type, COUNT(*) AS movement_count, COALESCE(SUM(quantity), 0) AS total_quantity
FROM stock_movements
WHERE (:date_from IS NULL OR created_at >= :date_from)
  AND (:date_to   IS NULL OR created_at <= :date_to)
  AND (:product_id IS NULL OR product_id = :product_id)
GROUP BY type
```

- Novo método `MovementRepository.summary_by_type(*, product_id, date_from,
  date_to)` → `Sequence[Row[tuple[MovementType, int, int]]]`. Reusa o mesmo padrão
  de filtros já existente no repo (`product_id`/`date_from`/`date_to`).
- O serviço **normaliza** o resultado: garante uma linha para cada
  `MovementType` (preenchendo `0`/`0` quando o tipo não apareceu no período),
  em ordem estável `in`, `out`, `adjustment`.

### Lógica pura (testável em unit)

```python
def build_movement_summary_rows(
    counts: dict[MovementType, tuple[int, int]],
) -> list[MovementsSummaryRow]:
    """Uma linha por MovementType, na ordem do enum, com zeros quando ausente."""
```

### Saída

```python
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

### Endpoint

`GET /reports/movements-summary?date_from=&date_to=&product_id=`
- Todos os filtros opcionais. `total_movements` = soma de `movement_count`.
- Acesso `report:read`.

## API

Router `app/api/v1/routes/reports.py`, prefixo `/reports`, tag `reports`,
`dependencies=[Depends(require_permission(Permission.REPORT_READ))]`, registrado em
`app/api/v1/router.py`.

| Método | Rota | Ação | Acesso |
|--------|------|------|--------|
| GET | `/reports/inventory-valuation` | Valor de estoque por produto + totais | MANAGER+ |
| GET | `/reports/movements-summary` | Movimentações agregadas por tipo no período | MANAGER+ |

## RBAC

`app/core/permissions.py`:
- adicionar `REPORT_READ = "report:read"` ao enum `Permission`.
- incluir `Permission.REPORT_READ` no conjunto `_MANAGER` (OPERATOR não recebe;
  ADMIN herda via `frozenset(Permission)`).

## Arquivos

**Novos:** `app/services/report.py`, `app/schemas/report.py`,
`app/api/v1/routes/reports.py`, `tests/unit/test_report_logic.py`,
`tests/integration/test_reports.py`.

**Editados:** `app/core/permissions.py` (REPORT_READ),
`app/repositories/product.py` (inventory_valuation),
`app/repositories/movement.py` (summary_by_type),
`app/api/v1/router.py` (include reports), `README.md`.

## Testes

**Unit** (`test_report_logic.py`, sem I/O):
- `build_movement_summary_rows` com todos os tipos presentes → 3 linhas corretas.
- com tipos ausentes → preenche `0/0`, mantém ordem `in, out, adjustment`.
- dict vazio → 3 linhas zeradas.

**Integration** (`test_reports.py`, Postgres real + AsyncClient + fakeredis):
- Valuation: 2 produtos com `quantity`/`unit_price` conhecidos → `items` ordenados
  por `stock_value` desc, `stock_value` por item correto, `summary.total_value` =
  soma esperada, `total_units`/`total_products` corretos.
- Valuation `only_active=true` (default) ignora produto inativo; `only_active=false`
  inclui.
- Valuation `supplier_id` filtra por fornecedor.
- Movements-summary: registra `in`/`out`/`adjustment` → linhas com
  `movement_count`/`total_quantity` corretos; tipo ausente vem zerado;
  `total_movements` correto.
- Movements-summary com `date_from` futuro → tudo zerado, `total_movements=0`.
- Sem autenticação → 401.

> Nota: 403 para OPERATOR não é testado — a fixture `auth_client` força admin
> (mesma limitação das iterações anteriores).

**Gates:** ruff + ruff format + mypy strict + pytest verdes contra Postgres real.

## Verificação

- `ruff check`/`format`, `mypy app`, `pytest` verdes.
- `docker compose up --build` sobe; via Swagger com token MANAGER:
  `GET /reports/inventory-valuation` e `GET /reports/movements-summary` retornam
  os relatórios; OPERATOR recebe 403.

## Fora de escopo (próximas iterações da Fase 3)

- **Export Excel** (openpyxl) destes mesmos relatórios — próxima iteração.
- **Tarefas assíncronas** (Celery/ARQ + Redis) para relatórios pesados/agendados.
- Relatório de saúde do estoque (alertas abertos/zerados/superestoque consolidados).
- Agrupamento temporal (por dia/semana) e séries históricas.
- Cache/materialização de relatórios.
