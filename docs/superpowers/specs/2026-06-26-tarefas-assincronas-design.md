# Design — Tarefas Assíncronas: Export de Relatório (Fase 3, iteração 4)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

Fecha a Fase 3 introduzindo **processamento assíncrono** no projeto. O caso de
uso é a **geração assíncrona dos exports `.xlsx`** entregues na iteração anterior:
em vez de gerar o arquivo na request (síncrono, pode ser pesado para catálogos
grandes), o cliente **enfileira** um job, **consulta o status** e **baixa** o
resultado quando pronto.

Reusa toda a base existente: `ReportService` (dados) e os builders de
`app/utils/excel.py` (serialização). A novidade é o **worker** e o ciclo
job → status → download.

## Decisões fechadas

- **Worker:** **ARQ** (async-native sobre Redis). Combina com o stack async
  (asyncpg/SQLAlchemy async) sem ponte sync; usa o Redis que já temos.
- **Caso de uso:** geração assíncrona dos 2 exports atuais (valuation e
  movements-summary).
- **Persistência do resultado:** **Redis com TTL**, via o **result store nativo
  do ARQ** (`keep_result`). Sem nova tabela/infra: o job *retorna* o arquivo e o
  ARQ guarda com expiração; a API lê pelo `job_id`.
- **Permissão:** reutiliza `report:read` (já aplicada no router `/reports`). Sem
  novas permissões.
- **DRY:** extrair helpers `*_export_file(report) -> ExportFile` em
  `app/utils/excel.py`, usados tanto pelas rotas síncronas quanto pelo worker.

## Fluxo

```
POST /reports/inventory-valuation/export-async   -> 202 {job_id, status:"queued"}
        │  enqueue_job("generate_inventory_valuation_export", ...)
        ▼
   [ARQ worker] gera o relatório (ReportService) + .xlsx (excel) -> retorna ExportFile
        │  ARQ guarda o resultado no Redis (keep_result = TTL)
        ▼
GET  /reports/jobs/{job_id}            -> {job_id, status}   (queued|in_progress|complete|failed|not_found→404)
GET  /reports/jobs/{job_id}/download   -> 200 .xlsx | 409 (processando/falhou) | 404
```

## Componentes

### Dependência

- runtime: `arq>=0.26.0` (traz a integração Redis; `redis` já é dependência).

### Config (`app/core/config.py` + `.env.example`)

- `REPORT_JOB_RESULT_TTL: int = 3600` — segundos que o resultado do job vive no
  Redis (ARQ `keep_result`).

### `app/utils/excel.py` — ExportFile + helpers

```python
@dataclass(frozen=True)
class ExportFile:
    filename: str
    media_type: str
    content: bytes

def inventory_valuation_export_file(report: InventoryValuationReport) -> ExportFile: ...
def movements_summary_export_file(report: MovementsSummaryReport) -> ExportFile: ...
```
- montam o `Workbook`, serializam (`workbook_to_bytes`) e definem o nome
  (`inventory-valuation-<data>.xlsx`). As rotas síncronas passam a usar esses
  helpers (sem duplicar a lógica de nome/serialização).

### `app/core/queue.py` — pool ARQ (singleton, espelha `core/redis.py`)

```python
def report_redis_settings() -> RedisSettings: ...   # host/port/db de settings
async def get_arq_pool() -> ArqRedis:               # cria/retorna o pool (lazy)
async def close_arq_pool() -> None: ...
```

### `app/worker/` — worker ARQ

- `app/worker/tasks.py`:
  ```python
  async def generate_inventory_valuation_export(ctx, *, supplier_id=None, only_active=True) -> dict:
      session_factory = ctx["session_factory"]
      async with session_factory() as session:
          report = await ReportService(session).inventory_valuation(...)
      f = inventory_valuation_export_file(report)
      return {"filename": f.filename, "media_type": f.media_type, "content": f.content}
  # idem generate_movements_summary_export(...)
  ```
  - a **session factory vem do `ctx`** (injetada no `on_startup`), o que torna a
    task testável com a sessão de teste (não acopla ao engine global).
  - retorno é um `dict` (picklável; `content` são bytes) — o ARQ persiste.
- `app/worker/settings.py`:
  ```python
  async def startup(ctx): ctx["session_factory"] = async_session_factory
  async def shutdown(ctx): await engine.dispose()

  class WorkerSettings:
      functions = [generate_inventory_valuation_export, generate_movements_summary_export]
      redis_settings = report_redis_settings()
      on_startup = startup
      on_shutdown = shutdown
      keep_result = settings.REPORT_JOB_RESULT_TTL
  ```
  - executável: `arq app.worker.settings.WorkerSettings`.

### `app/services/report_jobs.py` — abstração da fila

```python
class ReportJobQueue:
    def __init__(self, pool: ArqRedis): ...
    async def enqueue_inventory_valuation(self, *, supplier_id, only_active) -> str
    async def enqueue_movements_summary(self, *, product_id, date_from, date_to) -> str
    async def get_status(self, job_id: str) -> ReportJobState
    async def get_result(self, job_id: str) -> ExportFile | None
```
- `enqueue_*` chamam `pool.enqueue_job(<task>, ...)` e devolvem `job.job_id`
  (erro se `enqueue_job` retornar `None`).
- `get_status` mapeia o `arq.jobs.JobStatus` para `ReportJobState` (função pura
  `map_job_status`, testável): `deferred|queued→queued`, `in_progress→in_progress`,
  `complete`→`complete`/`failed` (via `result_info().success`), `not_found→not_found`.
- `get_result`: só quando `complete` e sucesso → reidrata `ExportFile`.
- Toda a interação com o ARQ fica encapsulada aqui (rotas e testes não tocam ARQ
  diretamente; testes injetam uma fila fake).

### Schemas (`app/schemas/report_job.py`)

```python
class ReportJobState(StrEnum):
    QUEUED = "queued"; IN_PROGRESS = "in_progress"
    COMPLETE = "complete"; FAILED = "failed"; NOT_FOUND = "not_found"

class ReportJobAccepted(BaseModel):
    job_id: str
    status: ReportJobState

class ReportJobStatus(BaseModel):
    job_id: str
    status: ReportJobState
```

### Dependência FastAPI (`app/dependencies/queue.py`)

```python
async def get_report_queue() -> ReportJobQueue:
    return ReportJobQueue(await get_arq_pool())
ReportQueue = Annotated[ReportJobQueue, Depends(get_report_queue)]
```

### Rotas (`app/api/v1/routes/reports.py`)

| Método | Rota | Ação | Resposta |
|--------|------|------|----------|
| POST | `/reports/inventory-valuation/export-async` | enfileira valuation | 202 `ReportJobAccepted` |
| POST | `/reports/movements-summary/export-async` | enfileira resumo | 202 `ReportJobAccepted` |
| GET | `/reports/jobs/{job_id}` | status do job | `ReportJobStatus` (404 se inexistente) |
| GET | `/reports/jobs/{job_id}/download` | baixa o `.xlsx` | 200 xlsx · 409 se processando/falhou · 404 |

- `download`: `not_found`→`NotFoundError` (404); `queued`/`in_progress`→
  `ConflictError("Relatório ainda em processamento.")` (409); `failed`→
  `ConflictError("A geração do relatório falhou.")` (409); `complete`→`Response`
  com bytes + `Content-Disposition`.
- Mesmos query params dos exports síncronos nos endpoints `export-async`.
- Auth: o router `/reports` já exige `report:read` em todas as rotas.

### Lifespan (`app/main.py`)

- adicionar `await close_arq_pool()` no shutdown (pool criado lazy no 1º enqueue).

### Docker (`docker/docker-compose.yml`)

- novo serviço `worker` reusando a imagem da API:
  ```yaml
  worker:
    build: { context: .., dockerfile: docker/Dockerfile }
    env_file: [../.env]
    depends_on: { db: {condition: service_healthy}, redis: {condition: service_healthy} }
    entrypoint: ["arq", "app.worker.settings.WorkerSettings"]   # sem migrations
    restart: unless-stopped
  ```
  - `entrypoint` sobrescreve o da API (não roda `alembic` — a API já migra).

## Arquivos

**Novos:** `app/core/queue.py`, `app/worker/__init__.py`, `app/worker/tasks.py`,
`app/worker/settings.py`, `app/services/report_jobs.py`,
`app/schemas/report_job.py`, `app/dependencies/queue.py`,
`tests/unit/test_report_jobs.py`, `tests/unit/test_export_file.py`,
`tests/integration/test_async_export.py`.

**Editados:** `pyproject.toml` (arq), `app/core/config.py` + `.env.example`
(`REPORT_JOB_RESULT_TTL`), `app/utils/excel.py` (ExportFile + helpers),
`app/api/v1/routes/reports.py` (rotas async + usa helpers), `app/main.py`
(close pool no shutdown), `docker/docker-compose.yml` (worker), `README.md`.

## Testes

**Unit** (sem DB/Redis — rodam no dev local):
- `test_export_file.py`: `*_export_file(report)` → `filename` no padrão
  (`inventory-valuation-2026-06-26.xlsx`), `media_type` = XLSX, `content` reabre
  com `load_workbook`.
- `test_report_jobs.py`: `map_job_status` cobre todos os `JobStatus`
  (deferred/queued→queued, in_progress, complete→complete, complete+falha→failed,
  not_found→not_found).

**Integration** (Postgres + fila fake; rodam no Docker do dev):
- task direto: `generate_inventory_valuation_export(ctx, ...)` com
  `ctx={"session_factory": <factory de teste>}` e produtos no DB → dict com
  `content` que reabre como `.xlsx` válido contendo os valores.
- endpoints com **fila fake** injetada (override de `get_report_queue`):
  - `POST .../export-async` → 202 + `job_id`, status inicial `queued`.
  - `GET /jobs/{id}` reflete o estado; **download** após `complete` devolve o
    `.xlsx` (bytes reabrem); enquanto `queued`/`in_progress` → 409; `id`
    desconhecido → 404.
  - sem autenticação → 401 nos novos endpoints.

> A fila fake evita exigir um broker ARQ real no teste; a integração ARQ↔Redis é
> validada manualmente no Docker (seção Verificação).

**Gates:** ruff + ruff format + mypy strict + pytest verdes.

## Verificação

- `ruff`/`mypy`/`pytest` verdes (unit local; integração no Docker do dev).
- `docker compose up --build` sobe `api` + `worker` + `db` + `redis`; via Swagger
  com token MANAGER: `POST .../export-async` → `job_id`; `GET /jobs/{id}` vira
  `complete`; `GET /jobs/{id}/download` baixa o `.xlsx`. Resultado some após o TTL.

## Fora de escopo (futuro / Fase 4)

- Jobs agendados/periódicos (cron do ARQ), reavaliação de alertas em lote.
- Notificação/webhook ao concluir; progresso granular.
- Observabilidade do worker (métricas/healthcheck dedicado) — entra na Fase 4.
- Storage durável (Postgres/objeto) para resultados grandes/auditáveis.
