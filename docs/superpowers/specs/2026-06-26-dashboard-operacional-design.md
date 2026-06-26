# Design — Dashboard Operacional (Fase 2, iteração 2)

**Data:** 2026-06-26
**Status:** Aprovado
**Projeto:** StockGuardian

## Contexto

A Fase 2 prevê um dashboard operacional. Esta iteração entrega a primeira fatia:
**contadores gerais** (produtos/fornecedores ativos, usuários) servidos por um
endpoint JSON com cache em Redis. Métricas mais ricas (valor de estoque, saúde
do estoque, movimentações recentes) ficam para iterações seguintes.

Independe do trabalho de alertas (contadores usam apenas entidades da Fase 1),
portanto a branch parte de `main`.

## Decisões fechadas

- **Métricas:** apenas contadores gerais — `active_products`, `active_suppliers`,
  `total_users`.
- **Cache:** Redis com TTL curto (default 60s), padrão cache-aside. Sem
  invalidação manual; expira por TTL.
- **Acesso:** MANAGER+ (`require_role(UserRole.MANAGER)`; ADMIN sempre passa).
- **Arquitetura:** helper genérico `cache.get_or_set` reutilizável +
  `DashboardService` que orquestra os COUNTs (abordagem A). Sem Redis inline no
  serviço, sem decorator de cache.

## Componentes

### `app/core/cache.py` — helper cache-aside
```python
async def get_or_set(redis, key, ttl, factory) -> dict:
    ...
```
- Tenta `redis.get(key)`; hit → `json.loads`.
- Miss → `value = await factory()`; `redis.set(key, json.dumps(value), ex=ttl)`;
  retorna `value`.
- `factory` é uma corrotina que devolve `dict` JSON-serializável.
- Genérico e reutilizável por futuros endpoints cacheados.

### `app/services/dashboard.py` — DashboardService
- `__init__(self, session, redis)`.
- `summary() -> dict`: envolve a query no `get_or_set` com key
  `dashboard:summary` e TTL `settings.DASHBOARD_CACHE_TTL`.
- `factory` interna calcula, reusando `BaseRepository.count(**filtros)`:
  - `active_products` = `ProductRepository(session).count(is_active=True)`
  - `active_suppliers` = `SupplierRepository(session).count(is_active=True)`
  - `total_users` = `UserRepository(session).count()`
- Retorna `dict` (cacheável direto; a rota valida em `DashboardSummary`).

### Config
- Novo `DASHBOARD_CACHE_TTL: int = 60` em `Settings` + `.env.example`.

## API

Router `app/api/v1/routes/dashboard.py`, prefixo `/dashboard`, registrado em
`app/api/v1/router.py`.

| Método | Rota | Ação | Acesso |
|--------|------|------|--------|
| GET | `/dashboard/summary` | contadores gerais | MANAGER+ |

- Injeta `DBSession` + `RedisClient` (dependências da Fase 1).
- `DashboardService(session, redis).summary()` → `DashboardSummary.model_validate(...)`.
- Read-only; sem escrita.

Schema (`app/schemas/dashboard.py`):
```python
class DashboardSummary(BaseModel):
    active_products: int
    active_suppliers: int
    total_users: int
```

## Arquivos

**Novos:** `app/core/cache.py`, `app/services/dashboard.py`,
`app/schemas/dashboard.py`, `app/api/v1/routes/dashboard.py`,
`tests/unit/test_cache.py`, `tests/integration/test_dashboard.py`.

**Editados:** `app/core/config.py`, `.env.example`, `app/api/v1/router.py`,
`README.md`.

## Testes

**Unit** (`get_or_set` com fakeredis, sem DB):
- miss → chama `factory`, grava no Redis, retorna o valor
- hit → NÃO chama `factory` (verificado por contador), retorna do cache
- `set` recebe o `ex=ttl` esperado

**Integration** (Postgres real + AsyncClient + fakeredis):
- com 2 produtos (1 inativo) + 1 fornecedor + usuários → `GET /dashboard/summary`
  retorna `active_products=1`, `active_suppliers=1`, contagem de usuários correta
- 2ª chamada após criar outro produto retorna o valor **cacheado** (inalterado
  dentro do TTL) — prova o cache
- sem autenticação → 401

> Nota: 403 para OPERATOR não é testado — a fixture `auth_client` força admin
> (mesma limitação das iterações anteriores).

**Gates:** ruff + ruff format + mypy strict + pytest verdes contra Postgres real
em container 3.13.

## Verificação

- `ruff check`/`format`, `mypy app`, `pytest` verdes
- `docker compose up --build` sobe; `GET /api/v1/dashboard/summary` com token
  MANAGER retorna os contadores; 2ª chamada serve do cache (Redis)

## Fora de escopo (iterações futuras)

- Valor total de estoque (`SUM(quantity * unit_price)`)
- Saúde do estoque (alertas abertos, zerados, superestoque)
- Movimentações recentes / janelas temporais
- Invalidação ativa de cache em eventos de escrita
