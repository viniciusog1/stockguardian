# Design — Detecção de Superestoque (Fase 3, iteração 1)

**Data:** 2026-06-26
**Status:** Aprovado
**Projeto:** StockGuardian

## Contexto

A Fase 2 entregou alertas de **estoque baixo** (`StockAlert`, ciclo
OPEN→ACKNOWLEDGED→RESOLVED, gerados na movimentação/update de produto). A Fase 3
começa com **detecção de superestoque** (excesso de estoque acima do máximo).

`Product.is_overstock` já existe (`max_stock is not None and quantity > max_stock`).
Em vez de criar um mecanismo paralelo, **estendemos o sistema de alertas** com um
discriminador `kind` (LOW_STOCK / OVERSTOCK), mantendo um feed único de alertas.

## Decisões fechadas

- **Modelo:** estender `StockAlert` com `kind: AlertKind`; reusar serviço, rotas e
  permissões de alerta (sem novas permissões).
- **Threshold:** generalizar `min_stock_at_trigger` → `threshold_at_trigger` (o
  limite cruzado: `min_stock` no low, `max_stock` no overstock).
- **Dedup:** 1 alerta ativo **por (produto, kind)** — índice único parcial passa a
  incluir `kind`.
- **Ciclo de vida:** idêntico ao atual (auto-resolve quando a condição cessa).
- **Avaliação:** `evaluate(product)` passa a checar os dois tipos por chamada.

## Modelo + migration

```python
class AlertKind(StrEnum):
    LOW_STOCK = "low_stock"
    OVERSTOCK = "overstock"
```

`StockAlert`:
- add `kind: Mapped[AlertKind]` (enum nativo `alert_kind`, `values_callable`,
  default `LOW_STOCK`).
- rename `min_stock_at_trigger` → `threshold_at_trigger`.
- `__table_args__`: índice único parcial agora em `(product_id, kind)`
  `WHERE status <> 'resolved'`.

**Migration `0003_stock_alerts_overstock`** (down_revision `0002_stock_alerts`):
1. cria enum `alert_kind` com valores `low_stock`, `overstock`.
2. `add_column` `kind` nullable → `UPDATE stock_alerts SET kind='low_stock'` →
   `alter_column` NOT NULL com `server_default='low_stock'`.
3. `alter_column` rename `min_stock_at_trigger` → `threshold_at_trigger`.
4. `drop_index uq_stock_alerts_active_per_product`; recria em `(product_id, kind)`
   parcial (`postgresql_where=text("status <> 'resolved'")`).

`downgrade`: reverte (recria índice antigo só em product_id, rename de volta, drop
column kind, drop type alert_kind).

## Serviço

`decide_alert_action` generaliza para condição booleana:
```python
def decide_alert_action(*, condition_met: bool, has_active: bool) -> AlertAction:
    if condition_met and not has_active:
        return AlertAction.OPEN
    if not condition_met and has_active:
        return AlertAction.RESOLVE
    return AlertAction.NOOP
```

`AlertService.evaluate(product) -> None` avalia os dois tipos:
```python
checks = [
    (AlertKind.LOW_STOCK, product.quantity <= product.min_stock, product.min_stock),
    (AlertKind.OVERSTOCK, product.is_overstock, product.max_stock),
]
for kind, condition, threshold in checks:
    active = await self.repo.get_active_for_product(product.id, kind)
    action = decide_alert_action(condition_met=condition, has_active=active is not None)
    if action is AlertAction.OPEN:
        # threshold nunca é None quando a condição é True
        # cria StockAlert(kind=kind, threshold_at_trigger=threshold, ...) via savepoint
        ...
    elif action is AlertAction.RESOLVE and active is not None:
        ...  # resolve + log alert_resolved(kind=...)
```
- Low e overstock são mutuamente exclusivos por construção; tratados de forma
  independente por `kind`.
- `AlertRepository.get_active_for_product(product_id, kind)` filtra por `kind`.
- Logs `alert_opened`/`alert_resolved` ganham `kind`.
- Concorrência: insert em savepoint; índice único `(product_id, kind)` é o backstop.

`evaluate` deixa de retornar o alerta (chamadores — movement/product service — já
ignoram o retorno).

## API

- `AlertRead`: rename `min_stock_at_trigger` → `threshold_at_trigger`; add
  `kind: AlertKind`.
- `AlertFilter`: add `kind: AlertKind | None`.
- `GET /alerts`: novo query param opcional `kind`.
- `acknowledge`/`resolve`: inalterados (mesmas permissões `alert:acknowledge` /
  `alert:resolve`, válidas para ambos os tipos).
- `AlertRepository.list_filtered`/`count_filtered`: aceitam `kind`.

Sem novas permissões (superestoque é um alerta).

## Arquivos

**Novos:** `migrations/versions/0003_stock_alerts_overstock.py`,
`tests/integration/test_overstock.py`.

**Editados:** `app/models/stock_alert.py` (AlertKind, kind, rename, índice),
`app/repositories/alert.py` (filtro kind), `app/services/alert.py`
(decide/evaluate generalizados), `app/schemas/alert.py` (AlertRead/AlertFilter),
`app/api/v1/routes/alerts.py` (query param kind),
`tests/unit/test_alert_logic.py` (nova assinatura), `README.md`.

## Testes

**Unit** (`test_alert_logic.py`):
- `decide_alert_action(condition_met, has_active)` → OPEN/RESOLVE/NOOP nos casos

**Integration** (`test_overstock.py`):
- produto `max_stock=10`; `IN` levando quantity=15 → abre alerta `kind=overstock`,
  `threshold_at_trigger=10`
- `OUT` voltando a ≤10 → overstock `resolved`
- low e overstock independentes (resolver/abrir um não afeta o outro)
- `GET /alerts?kind=overstock` filtra corretamente
- testes de low-stock existentes seguem verdes (produtos sem `max_stock`)

**Gates:** ruff + ruff format + mypy strict + pytest verdes contra Postgres real;
`alembic upgrade head` aplica a migration 0003 (com backfill).

## Verificação

- `ruff`/`mypy`/`pytest` verdes
- `docker compose up --build` aplica 0003; fluxo via Swagger: produto com
  `max_stock`, movimentar acima → alerta overstock; reduzir → resolve

## Fora de escopo (próximas iterações da Fase 3)

- Relatórios operacionais
- Export Excel (openpyxl)
- Tarefas assíncronas (Celery/ARQ + Redis)
