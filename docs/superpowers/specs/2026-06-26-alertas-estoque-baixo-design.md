# Design — Alertas de Estoque Baixo (Fase 2, iteração 1)

**Data:** 2026-06-26
**Status:** Aprovado
**Projeto:** StockGuardian

## Contexto

A Fase 1 (MVP) entregou produtos, fornecedores, movimentações e histórico. O
`Product` já calcula `is_low_stock` (`quantity <= min_stock`), mas nada reage a
isso. Esta iteração da Fase 2 introduz **alertas de estoque baixo persistidos e
gerados automaticamente**, dando ao sistema uma trilha operacional do tipo
"software real de empresa".

Demais frentes da Fase 2 (RBAC granular, dashboard, logs/auditoria) ficam para
iterações seguintes — este spec é focado só em alertas.

## Decisões fechadas

- **Forma:** alerta **persistido**, gerado no momento em que o estoque cruza o
  mínimo (não on-the-fly, não por job).
- **Ciclo de vida:** `OPEN → ACKNOWLEDGED → RESOLVED`. Auto-resolve quando o
  estoque recupera; operador pode reconhecer manualmente.
- **Dedup:** no máximo 1 alerta não-resolvido por produto.
- **Notificação:** apenas log estruturado (structlog) ao abrir/resolver. Sem
  email/webhook nesta fase (YAGNI).
- **Gatilho de avaliação:** após cada movimentação **e** após PATCH de produto
  que altere `min_stock`/`quantity`.
- **Arquitetura:** `AlertService.evaluate(product)` chamado explicitamente pelos
  serviços que mutam estoque, na mesma transação (abordagem A). Sem event
  listeners do SQLAlchemy (implícito/difícil de testar) nem domain events
  (over-engineering para 1 consumidor).

## Modelo de dados

Nova entidade `StockAlert` (`app/models/stock_alert.py`):

| Campo | Tipo | Nota |
|-------|------|------|
| `id` | UUID | PK (UUIDMixin) |
| `product_id` | FK → products | índice; `ondelete=CASCADE` |
| `status` | enum `AlertStatus` | `open` / `acknowledged` / `resolved` |
| `triggered_quantity` | int | estoque no momento da abertura |
| `min_stock_at_trigger` | int | snapshot do mínimo (auditoria) |
| `acknowledged_by` | FK → users, nullable | quem reconheceu |
| `acknowledged_at` | timestamptz, nullable | |
| `resolved_at` | timestamptz, nullable | preenchido ao resolver |
| `created_at` / `updated_at` | timestamptz | TimestampMixin |

- Enum nativo PG `alert_status` com `values_callable=lambda e: [m.value for m in e]`
  (persiste valores minúsculos — lição da Fase 1, onde o default do SAEnum grava
  os NOMES dos membros e diverge da migration).
- `AlertStatus(StrEnum)`: `OPEN="open"`, `ACKNOWLEDGED="acknowledged"`,
  `RESOLVED="resolved"`.
- **Invariante de dedup imposta pelo banco:** índice único parcial
  `UNIQUE (product_id) WHERE status <> 'resolved'`. Garante 1 alerta ativo por
  produto independentemente da aplicação.
- `Product.alerts` relationship (lazy, `cascade="all, delete-orphan"`).
- Migration `0002_stock_alerts`: cria enum + tabela + índice parcial.

## AlertService

`app/services/alert.py`. Recebe a `AsyncSession` (mesma dos demais serviços).

### `evaluate(product) -> StockAlert | None`
Chamado dentro da transação de quem alterou o estoque. Faz `flush`, não `commit`.

- `quantity <= min_stock` **e** sem alerta ativo (`OPEN`/`ACKNOWLEDGED`) →
  cria `OPEN` com snapshots; log `alert_opened`; retorna o alerta.
- `quantity > min_stock` **e** existe alerta ativo → `RESOLVED` + `resolved_at`;
  log `alert_resolved`.
- Caso contrário → no-op (idempotente; reavaliar não duplica nem reabre).
- Concorrência: se dois caminhos tentarem abrir simultaneamente, o índice único
  parcial faz o 2º `flush` levantar `IntegrityError`, tratado como "já existe
  ativo" (no-op).

### Operações manuais (commitam)
- `acknowledge(alert_id, user) -> StockAlert`: `OPEN → ACKNOWLEDGED`, grava
  `acknowledged_by/at`. Já resolvido → `ConflictError`.
- `resolve(alert_id) -> StockAlert`: fecho manual → `RESOLVED`. Já resolvido →
  `ConflictError`.
- `get(alert_id)`: `NotFoundError` se ausente.
- `list(filters, pagination) -> Page[StockAlert]`: filtra por `status`,
  `product_id`, ordena por `created_at desc`.

### Edge cases
- `min_stock=0` e `quantity=0`: `0 <= 0` dispara alerta (estoque zerado é alerta
  legítimo).

## Integração

Ambos injetam `AlertService` na própria sessão e chamam `evaluate` antes do commit:

- `MovementService.create` (`app/services/movement.py`): após setar
  `product.quantity = new_balance`, antes de `session.commit()`. Movimento +
  estoque + alerta atômicos.
- `ProductService.update` (`app/services/product.py`): quando o payload altera
  `min_stock` ou `quantity`, chama `evaluate(product)` antes do commit.

## API

Router `app/api/v1/routes/alerts.py`, prefixo `/alerts`, registrado no
`api/v1/router.py`.

| Método | Rota | Ação | Acesso |
|--------|------|------|--------|
| GET | `/alerts` | lista (filtros `status`, `product_id`, paginação) | autenticado |
| GET | `/alerts/{id}` | detalhe | autenticado |
| POST | `/alerts/{id}/acknowledge` | reconhecer | OPERATOR+ |
| POST | `/alerts/{id}/resolve` | resolver manual | MANAGER+ |

Sem endpoint de criação manual — alertas só nascem por avaliação automática.
Reusa `require_role`, `Pagination`, exceções de domínio e o envelope de erro
padronizado da Fase 1.

Schemas (`app/schemas/alert.py`): `AlertRead`, `AlertFilter`.

## Arquivos

**Novos:** `models/stock_alert.py`, `repositories/alert.py`, `services/alert.py`,
`schemas/alert.py`, `api/v1/routes/alerts.py`, `migrations/versions/0002_*.py`,
`tests/unit/test_alert_logic.py`, `tests/integration/test_alerts.py`.

**Editados:** `services/movement.py`, `services/product.py`, `models/__init__.py`,
`api/v1/router.py`.

## Testes

**Unit** (`AlertService`, repo mockado / lógica pura):
- abre ao cruzar o mínimo; não duplica se já aberto
- auto-resolve ao recuperar estoque
- no-op quando estado já correto (idempotência)
- `min_stock=0, quantity=0` → abre
- acknowledge/resolve em estado inválido → `ConflictError`

**Integration** (Postgres real + AsyncClient):
- OUT cruzando o mínimo → cria `OPEN` (`GET /alerts?status=open`)
- IN recuperando → vira `RESOLVED`
- 2ª OUT abaixo do mínimo não cria 2º alerta (índice parcial)
- PATCH subindo `min_stock` acima do estoque → abre alerta
- `acknowledge` → `ACKNOWLEDGED` + `acknowledged_by`; `resolve` → `RESOLVED`
- permissões: OPERATOR reconhece, MANAGER resolve, role insuficiente → 403

## Verificação

- `ruff check` + `ruff format --check` limpos
- `mypy app` (strict) limpo
- `pytest` verde (unit + integration) contra Postgres real em container 3.13
- `alembic upgrade head` aplica a migration `0002` sem erro
- Fluxo manual via Swagger: movimentar até abaixo do mínimo → alerta aparece →
  reconhecer → repor estoque → alerta resolvido

## Fora de escopo (iterações futuras)

- RBAC granular por permissões nomeadas
- Dashboard operacional (consumirá contagem de alertas)
- Notificações email/webhook (fase async)
- Alertas de superestoque (Fase 3 — `is_overstock` já existe no model)
