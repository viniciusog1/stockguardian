# Design — Export Excel dos Relatórios (Fase 3, iteração 3)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

A iteração anterior entregou dois relatórios JSON sob `/reports`
(`inventory-valuation` e `movements-summary`), já com formato tabular (linhas +
resumo) pensado para export. Esta iteração adiciona o **download `.xlsx`** desses
mesmos relatórios via **openpyxl**.

Não há mudança de schema do banco nem de regra de negócio: o export é uma camada
de **apresentação** sobre os dados que o `ReportService` já produz. A branch parte
de `main`.

## Decisões fechadas

- **API:** endpoints `/export` dedicados (não content-negotiation por
  `?format`), mantendo os endpoints JSON intactos e com `response_model` limpo:
  - `GET /reports/inventory-valuation/export`
  - `GET /reports/movements-summary/export`
- **Escopo:** apenas os 2 relatórios atuais. Histórico detalhado de movimentações
  fica fora.
- **Reuso:** os endpoints de export chamam o **mesmo `ReportService`** (mesmos
  filtros/params), depois serializam o resultado em `.xlsx`. Sem duplicar query.
- **Camada de serialização:** módulo puro `app/utils/excel.py` que recebe o
  schema do relatório e devolve um `Workbook` (testável sem DB). A rota só liga
  serviço → builder → resposta HTTP.
- **Permissão:** reutiliza `report:read` (MANAGER+). Sem novas permissões.
- **Dependência:** adicionar `openpyxl` às dependências de runtime e
  `types-openpyxl` às de dev (mypy strict). Docker já instala via `pyproject`.

## Componentes

### `app/utils/excel.py`

```python
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

def inventory_valuation_workbook(report: InventoryValuationReport) -> Workbook: ...
def movements_summary_workbook(report: MovementsSummaryReport) -> Workbook: ...
def workbook_to_bytes(workbook: Workbook) -> bytes: ...   # salva em BytesIO
```

**Planilha `inventory-valuation`** (aba "Valuation"):
- Linha 1: título + `Gerado em: <generated_at ISO>`.
- Linha de cabeçalho: `SKU | Produto | Quantidade | Preço unitário | Valor em estoque`
  (em negrito).
- Uma linha por item; colunas de dinheiro com `number_format` contábil
  (`#,##0.00`).
- Linha em branco + bloco de totais: `Total de produtos`, `Total de unidades`,
  `Valor total em estoque`.

**Planilha `movements-summary`** (aba "Movimentações"):
- Linha 1: título + período (`date_from`/`date_to` ou "todos") + `generated_at`.
- Cabeçalho: `Tipo | Qtd. de movimentações | Quantidade total`.
- 3 linhas (in/out/adjustment, na ordem do enum) + linha de total
  (`total_movements`).

`workbook_to_bytes` salva o workbook em um `io.BytesIO` e retorna `getvalue()`.

### Rotas (`app/api/v1/routes/reports.py`)

Cada export:
1. obtém o relatório via `ReportService` (mesmos params do JSON);
2. monta o `Workbook` com o builder e serializa com `workbook_to_bytes`;
3. retorna `fastapi.Response(content=..., media_type=XLSX_MEDIA_TYPE,
   headers={"Content-Disposition": f'attachment; filename="<nome>.xlsx"'})`.

Nome do arquivo inclui a data de geração, ex.:
`inventory-valuation-2026-06-26.xlsx`, `movements-summary-2026-06-26.xlsx`.

| Método | Rota | Ação | Acesso |
|--------|------|------|--------|
| GET | `/reports/inventory-valuation/export` | Valuation em `.xlsx` | MANAGER+ |
| GET | `/reports/movements-summary/export` | Resumo de movimentações em `.xlsx` | MANAGER+ |

Os params de filtro são idênticos aos dos endpoints JSON correspondentes.

## mypy / openpyxl

openpyxl não embarca `py.typed`. Usar **`types-openpyxl`** (dev) para tipar
`Workbook`. Se os stubs gerarem ruído sob strict, fallback é um override
`module = ["openpyxl.*"]` com `ignore_missing_imports = true` — decidido na
verificação.

## Arquivos

**Novos:** `app/utils/excel.py`, `tests/unit/test_excel_export.py`,
`tests/integration/test_reports_export.py`.

**Editados:** `pyproject.toml` (openpyxl + types-openpyxl),
`app/api/v1/routes/reports.py` (2 rotas de export), `README.md`.

## Testes

**Unit** (`test_excel_export.py`, sem DB — constrói o schema na mão):
- `inventory_valuation_workbook`: célula de cabeçalho correta; linha de item com
  SKU/quantidade/valor esperados; bloco de totais com `total_value`.
- `movements_summary_workbook`: 3 linhas por tipo na ordem certa; linha de total
  com `total_movements`.
- `workbook_to_bytes` devolve bytes que **reabrem** como workbook válido
  (`load_workbook(BytesIO(...))`) com a aba esperada — prova que o `.xlsx` é
  íntegro.

**Integration** (`test_reports_export.py`, Postgres real + AsyncClient):
- `GET /reports/inventory-valuation/export` → 200, `content-type` = XLSX,
  `content-disposition` com `attachment; filename=...xlsx`; bytes carregam via
  `load_workbook` e contêm os valores dos produtos criados.
- `GET /reports/movements-summary/export` → 200 + workbook válido com os
  agregados esperados.
- Sem autenticação → 401 nos dois.

> Nota: 403 para OPERATOR não é testado — a fixture `auth_client` força admin
> (mesma limitação das iterações anteriores).

**Gates:** ruff + ruff format + mypy strict + pytest verdes.

## Verificação

- `ruff`/`mypy`/`pytest` verdes.
- `docker compose up --build` instala openpyxl; via Swagger com token MANAGER, os
  dois endpoints `/export` baixam `.xlsx` abríveis no Excel/LibreOffice.

## Fora de escopo (próximas iterações da Fase 3)

- **Tarefas assíncronas** (Celery/ARQ + Redis) — gerar/_agendar_ exports pesados
  em background e disponibilizar por download posterior.
- Export do histórico detalhado de movimentações (`GET /movements`).
- Outros formatos (CSV/PDF) e estilos avançados de planilha (gráficos, merge).
