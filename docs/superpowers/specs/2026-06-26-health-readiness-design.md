# Design — Health/Readiness Probes (Fase 4, iteração 2)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

Continua a Fase 4 (observabilidade/operação). Hoje existe apenas `/health`
(liveness simples, definido inline no `main.py`). Para orquestradores
(Kubernetes/compose healthchecks) é importante **separar liveness de readiness**:

- **Liveness** (`/health`): o processo está vivo? Responde 200 sempre que a app
  consegue responder (sem checar dependências).
- **Readiness** (`/health/ready`): a app está pronta para receber tráfego? Checa
  **DB** e **Redis** de verdade; 200 se tudo ok, **503** se alguma dependência
  estiver indisponível.

Sem mudança de schema. Branch parte de `main`.

## Decisões fechadas

- **Rotas na raiz** (fora de `/api/v1`), **sem autenticação** — padrão de probes,
  como o `/health` atual.
- **Liveness** mantém o shape atual (`{"status":"ok","service":...}`) p/ não
  quebrar nada.
- **Readiness** checa `database` (`SELECT 1`) e `redis` (`ping`), cada um isolado
  em try/except; resposta estruturada por dependência. Status HTTP: 200 (ready)
  ou 503 (not ready).
- **Camadas:** `HealthService` faz os checks; rota fina decide o status code.
- Mover o `/health` inline para um router dedicado (`app/api/health.py`) e
  registrá-lo na raiz.

## Componentes

### Schemas (`app/schemas/health.py`)
```python
class LivenessResponse(BaseModel):
    status: str
    service: str

class CheckResult(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None

class ReadinessResponse(BaseModel):
    ready: bool
    checks: dict[str, CheckResult]   # ex.: {"database": {...}, "redis": {...}}
```

### Serviço (`app/services/health.py`)
```python
class HealthService:
    def __init__(self, session: AsyncSession, redis: Redis): ...
    async def _check_db(self) -> CheckResult:      # SELECT 1; ok|error(+detail)
    async def _check_redis(self) -> CheckResult:   # ping;     ok|error(+detail)
    async def readiness(self) -> ReadinessResponse:
        checks = {"database": ..., "redis": ...}
        return ReadinessResponse(
            ready=all(c.status == "ok" for c in checks.values()), checks=checks
        )
```
- cada check captura exceção e devolve `error` + `detail` curto (mensagem da
  exceção) — sem derrubar a request.

### Rotas (`app/api/health.py`, sem prefixo)
```python
router = APIRouter(tags=["health"])

@router.get("/health", response_model=LivenessResponse, summary="Liveness probe")
async def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok", service=settings.PROJECT_NAME)

@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(session: DBSession, redis: RedisClient, response: Response) -> ReadinessResponse:
    result = await HealthService(session, redis).readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
```

### `app/main.py`
- remover o `@app.get("/health")` inline; `app.include_router(health.router)`
  (raiz, sem prefixo). Mantém ordem: middleware → handlers → api_router → health
  → metrics.

## Arquivos

**Novos:** `app/schemas/health.py`, `app/services/health.py`, `app/api/health.py`,
`tests/unit/test_health.py`, `tests/integration/test_health.py`.

**Editados:** `app/main.py`, `README.md`.

## Testes

**Unit** (`test_health.py`, sem I/O real — fakes simples):
- `HealthService` com fakes onde `session.execute`/`redis.ping` funcionam →
  `ready=True`, ambos `ok`.
- fake de redis cujo `ping` levanta → `ready=False`, `redis.status=="error"`,
  `database.status=="ok"`.
- fake de session cujo `execute` levanta → `database.status=="error"`.

**Integration** (`test_health.py`, Postgres real + fakeredis):
- `GET /health` → 200, `{"status":"ok"}`.
- `GET /health/ready` → 200, `ready=True`, checks db+redis `ok`.
- readiness com Redis quebrado: override de `get_redis_client` por um fake cujo
  `ping` levanta → `GET /health/ready` → **503**, `ready=False`,
  `redis.status=="error"`, `database.status=="ok"`.
- probes acessíveis **sem** autenticação.

**Gates:** ruff + ruff format + mypy strict + pytest verdes.

## Verificação

- `ruff`/`mypy`/`pytest` (unit local; integração no Docker).
- `docker compose up`: `GET /health` 200; `GET /health/ready` 200 com tudo no ar;
  derrubando o Redis, readiness vira 503 (liveness segue 200).

## Fora de escopo (próximas iterações da Fase 4)

- Usar as probes nos healthchecks do `docker-compose`/manifests (entra no deploy).
- Tracing OpenTelemetry.
- Stack de scrape (Prometheus + Grafana).
- Checagem de readiness do worker ARQ.
