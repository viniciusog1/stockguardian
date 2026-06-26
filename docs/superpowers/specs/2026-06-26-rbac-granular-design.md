# Design — RBAC Granular (Fase 2, iteração 3)

**Data:** 2026-06-26
**Status:** Aprovado
**Projeto:** StockGuardian

## Contexto

Hoje a autorização usa `require_role(*roles)` com 3 papéis fixos
(ADMIN/MANAGER/OPERATOR); ADMIN faz bypass de tudo. Esta iteração migra para
**permissões nomeadas granulares** (ex.: `product:write`, `alert:resolve`),
mantendo as roles como *bundles* de permissões definidos no código. É o último
item da Fase 2.

O **comportamento de acesso permanece idêntico** ao atual — apenas o mecanismo
muda de "checar role" para "checar permissão".

## Decisões fechadas

- **Modelo:** permissões no código (enum); cada role mapeia a um `frozenset` de
  permissões. Sem tabelas no banco.
- **ADMIN:** recebe todas as permissões (preserva o bypass atual), sem caso
  especial no checker.
- **Exposição:** `GET /auth/me` passa a retornar a lista de permissões do
  usuário (derivada da role, resolvida server-side). JWT não muda.
- **Mecanismo:** `require_permission(*perms)` substitui `require_role` nas rotas;
  `require_role` é removido após a migração.

## Componentes

### `app/core/permissions.py`
```python
class Permission(StrEnum):
    SUPPLIER_READ = "supplier:read"
    SUPPLIER_WRITE = "supplier:write"
    PRODUCT_READ = "product:read"
    PRODUCT_WRITE = "product:write"
    MOVEMENT_READ = "movement:read"
    MOVEMENT_CREATE = "movement:create"
    ALERT_READ = "alert:read"
    ALERT_ACKNOWLEDGE = "alert:acknowledge"
    ALERT_RESOLVE = "alert:resolve"
    DASHBOARD_READ = "dashboard:read"
    USER_MANAGE = "user:manage"
```

Mapa `ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]]`:

| Permissão | OPERATOR | MANAGER | ADMIN |
|-----------|:--:|:--:|:--:|
| supplier:read, product:read, movement:read, alert:read | ✅ | ✅ | ✅ |
| movement:create, alert:acknowledge | ✅ | ✅ | ✅ |
| supplier:write, product:write, alert:resolve, dashboard:read | — | ✅ | ✅ |
| user:manage | — | — | ✅ |

- ADMIN = `frozenset(Permission)` (todas).
- `permissions_for(role) -> frozenset[Permission]`.
- `has_permissions(role, *perms) -> bool` (helper puro p/ checagem e testes).

Granularidade: CRUD genérico em `:read`/`:write`; ações de domínio finas
(`alert:acknowledge` vs `alert:resolve`, `movement:create`). `:write` pode ser
dividido em create/update/delete no futuro sem quebrar o resto.

### `app/dependencies/auth.py`
```python
def require_permission(*required: Permission) -> Callable[[User], Awaitable[User]]:
    async def _checker(current_user: CurrentUser) -> User:
        if has_permissions(current_user.role, *required):
            return current_user
        raise AuthorizationError(
            "Permissão insuficiente para esta operação.",
            details={"required": [p.value for p in required]},
        )
    return _checker
```
`require_role` é removido (nenhuma rota o usa após a migração).

### Migração das rotas (`require_role` → `require_permission`)
- `products`: escrita → `PRODUCT_WRITE`
- `suppliers`: escrita → `SUPPLIER_WRITE`
- `movements`: criação → `MOVEMENT_CREATE`
- `alerts`: acknowledge → `ALERT_ACKNOWLEDGE`; resolve → `ALERT_RESOLVE`
- `dashboard`: → `DASHBOARD_READ`
- `users`: dependência do router → `USER_MANAGE`

(Leituras que hoje só exigem autenticação continuam só exigindo autenticação.)

### `/auth/me`
Novo schema `UserMe(UserRead)` com `permissions: list[str]`, usado **apenas** no
`/auth/me`. Preenchido na rota com `sorted(p.value for p in permissions_for(user.role))`.
Listagens de usuários seguem usando `UserRead` (sem inflar com permissões).

## Arquivos

**Novos:** `app/core/permissions.py`, `tests/unit/test_permissions.py`,
`tests/integration/test_rbac.py`.

**Editados:** `app/dependencies/auth.py` (add `require_permission`, remove
`require_role`), `app/schemas/user.py` (add `UserMe`),
`app/api/v1/routes/{auth,products,suppliers,movements,alerts,dashboard,users}.py`
(trocar guards), `tests/conftest.py` (fixtures por role), `README.md`.

## Testes

**Unit** (`permissions.py`, dado puro):
- `permissions_for` para cada role retorna o conjunto esperado
- ADMIN contém todas as `Permission`
- `has_permissions(role, *perms)` True/False nos casos certos

**Conftest:** fixture `make_auth_client(role)` cria usuário com a role + override
de `get_current_active_user`; expõe `operator_client` e `manager_client` (além do
`auth_client` admin já existente).

**Integration:**
- `GET /auth/me` retorna `permissions` coerente com a role
- operator: `POST /movements` 201; `POST /products` **403**;
  `alerts/{id}/acknowledge` 200; `alerts/{id}/resolve` **403**
- manager: `POST /products` 201; `GET /dashboard/summary` 200; `POST /users` **403**
- admin: `POST /users` 201
- corpo do 403: `code = authorization_error`, `details.required` presente

**Gates:** ruff + ruff format + mypy strict + pytest verdes contra Postgres real
em container 3.13.

## Verificação

- `ruff`/`mypy`/`pytest` verdes
- `docker compose up --build` sobe; `GET /auth/me` mostra permissões; um OPERATOR
  recebe 403 ao tentar criar produto; MANAGER cria produto e vê dashboard

## Fora de escopo

- Permissões/roles geridas em banco (atribuição dinâmica)
- Overrides por usuário individual
- Permissões como claim no JWT
- Dividir `:write` em create/update/delete
