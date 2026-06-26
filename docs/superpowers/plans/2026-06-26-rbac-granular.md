# RBAC Granular — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar a autorização de `require_role` para permissões nomeadas granulares (`require_permission`), mantendo as roles como bundles no código e expondo as permissões em `GET /auth/me`.

**Architecture:** `app/core/permissions.py` define o enum `Permission` e o mapa `role → frozenset[Permission]` (ADMIN = todas). `require_permission(*perms)` substitui `require_role` nas rotas. Comportamento de acesso idêntico ao atual.

**Tech Stack:** FastAPI (Depends), Pydantic v2, pytest. Segue os padrões das fases anteriores.

Spec: `docs/superpowers/specs/2026-06-26-rbac-granular-design.md`.

---

## Convenção de testes (ambiente)

Igual às iterações anteriores. **Subir infra (uma vez):**
```bash
cd /Users/viniciusoliveira/Documents/stockguardian
cp -n .env.example .env
docker compose -f docker/docker-compose.yml up -d db redis
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian -c "CREATE DATABASE stockguardian_test;" 2>/dev/null || true
```

**Atalho TESTRUN `<CMD>`:**
```bash
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
docker run --rm --network stockguardian_default -v "$PWD":/app -w /app \
  -e TEST_DATABASE_URL="postgresql+asyncpg://stockguardian:stockguardian@db:5432/stockguardian_test" \
  -e SECRET_KEY="ci-test-secret" \
  python:3.13-slim bash -c "pip install -q uv && uv pip install --system -q '.[dev]' && <CMD>"
```

---

## Task 1: Módulo de permissões + unit tests

**Files:**
- Create: `app/core/permissions.py`
- Test: `tests/unit/test_permissions.py`

- [ ] **Step 1: Escrever os testes falhos**

`tests/unit/test_permissions.py`:
```python
"""Testes unitários do mapa de permissões (dado puro)."""

from __future__ import annotations

import pytest

from app.core.permissions import Permission, has_permissions, permissions_for
from app.models.user import UserRole

pytestmark = pytest.mark.unit


def test_admin_has_all_permissions() -> None:
    assert permissions_for(UserRole.ADMIN) == frozenset(Permission)


def test_operator_subset() -> None:
    perms = permissions_for(UserRole.OPERATOR)
    assert Permission.MOVEMENT_CREATE in perms
    assert Permission.ALERT_ACKNOWLEDGE in perms
    assert Permission.PRODUCT_WRITE not in perms
    assert Permission.ALERT_RESOLVE not in perms
    assert Permission.USER_MANAGE not in perms


def test_manager_has_writes_but_not_user_manage() -> None:
    perms = permissions_for(UserRole.MANAGER)
    assert Permission.PRODUCT_WRITE in perms
    assert Permission.ALERT_RESOLVE in perms
    assert Permission.DASHBOARD_READ in perms
    assert Permission.USER_MANAGE not in perms


def test_has_permissions_helper() -> None:
    assert has_permissions(UserRole.MANAGER, Permission.PRODUCT_WRITE)
    assert has_permissions(
        UserRole.OPERATOR, Permission.MOVEMENT_CREATE, Permission.ALERT_ACKNOWLEDGE
    )
    assert not has_permissions(UserRole.OPERATOR, Permission.PRODUCT_WRITE)
```

- [ ] **Step 2: Rodar — deve falhar**

TESTRUN `pytest tests/unit/test_permissions.py -q`
Expected: FAIL — `ModuleNotFoundError: app.core.permissions`.

- [ ] **Step 3: Implementar o módulo**

`app/core/permissions.py`:
```python
"""Permissões nomeadas (RBAC granular).

Fonte única de verdade do que cada role pode fazer. As rotas checam permissões
(via `require_permission`), não roles diretamente.
"""

from __future__ import annotations

from enum import StrEnum

from app.models.user import UserRole


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


_OPERATOR: frozenset[Permission] = frozenset(
    {
        Permission.SUPPLIER_READ,
        Permission.PRODUCT_READ,
        Permission.MOVEMENT_READ,
        Permission.MOVEMENT_CREATE,
        Permission.ALERT_READ,
        Permission.ALERT_ACKNOWLEDGE,
    }
)
_MANAGER: frozenset[Permission] = _OPERATOR | frozenset(
    {
        Permission.SUPPLIER_WRITE,
        Permission.PRODUCT_WRITE,
        Permission.ALERT_RESOLVE,
        Permission.DASHBOARD_READ,
    }
)
_ADMIN: frozenset[Permission] = frozenset(Permission)  # todas

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.OPERATOR: _OPERATOR,
    UserRole.MANAGER: _MANAGER,
    UserRole.ADMIN: _ADMIN,
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def has_permissions(role: UserRole, *perms: Permission) -> bool:
    granted = permissions_for(role)
    return all(p in granted for p in perms)
```

- [ ] **Step 4: Rodar — deve passar**

TESTRUN `pytest tests/unit/test_permissions.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**
```bash
git add app/core/permissions.py tests/unit/test_permissions.py
git commit -m "feat(rbac): módulo de permissões + unit tests"
```

---

## Task 2: Dependência `require_permission`

**Files:**
- Modify: `app/dependencies/auth.py`

- [ ] **Step 1: Adicionar require_permission (mantendo require_role por ora)**

Em `app/dependencies/auth.py`, adicionar o import no topo:
```python
from app.core.permissions import Permission, has_permissions
```
E adicionar a função (após `require_role`):
```python
def require_permission(*required: Permission) -> Callable[[User], Awaitable[User]]:
    """Factory de dependência que exige todas as permissões informadas."""

    async def _checker(current_user: CurrentUser) -> User:
        if has_permissions(current_user.role, *required):
            return current_user
        raise AuthorizationError(
            "Permissão insuficiente para esta operação.",
            details={"required": [p.value for p in required]},
        )

    return _checker
```

- [ ] **Step 2: Verificar import**

TESTRUN `python -c "from app.dependencies.auth import require_permission; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add app/dependencies/auth.py
git commit -m "feat(rbac): dependência require_permission"
```

---

## Task 3: Schema UserMe + /auth/me com permissões

**Files:**
- Modify: `app/schemas/user.py`
- Modify: `app/api/v1/routes/auth.py`

- [ ] **Step 1: Adicionar UserMe**

Em `app/schemas/user.py`, ao final, adicionar:
```python
class UserMe(UserRead):
    permissions: list[str]
```

- [ ] **Step 2: Atualizar a rota /auth/me**

Em `app/api/v1/routes/auth.py`:
- adicionar imports:
```python
from app.core.permissions import permissions_for
from app.schemas.user import UserMe
```
- trocar a rota `me` por:
```python
@router.get("/me", response_model=UserMe)
async def me(current_user: CurrentUser) -> UserMe:
    perms = sorted(p.value for p in permissions_for(current_user.role))
    data = UserRead.model_validate(current_user).model_dump()
    return UserMe(**data, permissions=perms)
```
(`UserRead` já está importado no arquivo.)

- [ ] **Step 3: Verificar boot**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**
```bash
git add app/schemas/user.py app/api/v1/routes/auth.py
git commit -m "feat(rbac): /auth/me expõe permissões (UserMe)"
```

---

## Task 4: Migrar rotas para require_permission + remover require_role

**Files:**
- Modify: `app/api/v1/routes/{products,suppliers,movements,alerts,dashboard,users}.py`
- Modify: `app/dependencies/auth.py`

- [ ] **Step 1: products.py**

Em `app/api/v1/routes/products.py`:
- trocar import `from app.models.user import UserRole` por
  `from app.core.permissions import Permission`
- trocar `ManagerUp = Depends(require_role(UserRole.MANAGER))` por
  `CanWrite = Depends(require_permission(Permission.PRODUCT_WRITE))`
- atualizar o import de auth para `from app.dependencies.auth import CurrentUser, require_permission`
- substituir as 3 ocorrências `dependencies=[ManagerUp]` por `dependencies=[CanWrite]`

- [ ] **Step 2: suppliers.py**

Em `app/api/v1/routes/suppliers.py`, igual ao products:
- import `from app.core.permissions import Permission`; `from app.dependencies.auth import CurrentUser, require_permission`
- `CanWrite = Depends(require_permission(Permission.SUPPLIER_WRITE))`
- as 3 ocorrências `dependencies=[ManagerUp]` → `dependencies=[CanWrite]`

- [ ] **Step 3: movements.py**

Em `app/api/v1/routes/movements.py`:
- import `from app.core.permissions import Permission`; `from app.dependencies.auth import CurrentUser, require_permission`
- trocar `OperatorUp = Depends(require_role(UserRole.OPERATOR, UserRole.MANAGER))` por
  `CanCreate = Depends(require_permission(Permission.MOVEMENT_CREATE))`
- a ocorrência `dependencies=[OperatorUp]` → `dependencies=[CanCreate]`
- remover o import de `UserRole` se ficar sem uso

- [ ] **Step 4: alerts.py**

Em `app/api/v1/routes/alerts.py`:
- import `from app.core.permissions import Permission`; `from app.dependencies.auth import CurrentUser, require_permission`
- trocar:
```python
OperatorUp = Depends(require_role(UserRole.OPERATOR, UserRole.MANAGER))
ManagerUp = Depends(require_role(UserRole.MANAGER))
```
por:
```python
CanAcknowledge = Depends(require_permission(Permission.ALERT_ACKNOWLEDGE))
CanResolve = Depends(require_permission(Permission.ALERT_RESOLVE))
```
- `dependencies=[OperatorUp]` (acknowledge) → `dependencies=[CanAcknowledge]`
- `dependencies=[ManagerUp]` (resolve) → `dependencies=[CanResolve]`
- remover import de `UserRole` se sem uso

- [ ] **Step 5: dashboard.py**

Em `app/api/v1/routes/dashboard.py`:
- import `from app.core.permissions import Permission`; `from app.dependencies.auth import require_permission`
- trocar `dependencies=[Depends(require_role(UserRole.MANAGER))]` por
  `dependencies=[Depends(require_permission(Permission.DASHBOARD_READ))]`
- remover import de `UserRole` se sem uso

- [ ] **Step 6: users.py**

Em `app/api/v1/routes/users.py`:
- import `from app.core.permissions import Permission`; `from app.dependencies.auth import require_permission`
- trocar `dependencies=[Depends(require_role(UserRole.ADMIN))]` por
  `dependencies=[Depends(require_permission(Permission.USER_MANAGE))]`
- remover import de `UserRole` se sem uso

- [ ] **Step 7: Remover require_role**

Em `app/dependencies/auth.py`, remover a função `require_role` inteira (não é mais
referenciada). Manter `require_permission`, `get_current_user`,
`get_current_active_user`, `CurrentUser`.

- [ ] **Step 8: Garantir que nada referencia require_role**

TESTRUN `grep -rn "require_role" app/ && echo FOUND || echo CLEAN`
Expected: `CLEAN`.

- [ ] **Step 9: Verificar boot + suíte existente**

TESTRUN `python -c "from app.main import create_app; create_app(); print('ok')" && pytest tests/integration -q`
Expected: `ok` e os testes de integração existentes verdes (auth_client é admin → todas as permissões; comportamento preservado).

- [ ] **Step 10: Commit**
```bash
git add app/api/v1/routes app/dependencies/auth.py
git commit -m "refactor(rbac): rotas usam require_permission; remove require_role"
```

---

## Task 5: Fixtures por role no conftest

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Adicionar fixtures operator_client e manager_client**

Em `tests/conftest.py`, ao final do arquivo, adicionar:
```python
async def _client_as(client: AsyncClient, db_session: AsyncSession, role: UserRole) -> AsyncClient:
    user = User(
        email=f"{role.value}@test.com",
        hashed_password=hash_password("Pw@123456"),
        full_name=f"{role.value.title()} Teste",
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    app = client._app  # type: ignore[attr-defined]
    app.dependency_overrides[get_current_active_user] = lambda: user
    return client


@pytest_asyncio.fixture
async def operator_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    return await _client_as(client, db_session, UserRole.OPERATOR)


@pytest_asyncio.fixture
async def manager_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    return await _client_as(client, db_session, UserRole.MANAGER)
```
(`User`, `UserRole`, `hash_password`, `get_current_active_user`, `AsyncSession`,
`AsyncClient` já são importados no conftest.)

- [ ] **Step 2: Verificar coleta**

TESTRUN `pytest tests/ -q --co >/dev/null && echo OK`
Expected: `OK` (coleta sem erros de import).

- [ ] **Step 3: Commit**
```bash
git add tests/conftest.py
git commit -m "test(rbac): fixtures operator_client e manager_client"
```

---

## Task 6: Testes de integração RBAC

**Files:**
- Test: `tests/integration/test_rbac.py`

- [ ] **Step 1: Escrever os testes**

`tests/integration/test_rbac.py`:
```python
"""Integração: autorização granular por permissão."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.stock_alert import AlertStatus, StockAlert
from app.models.supplier import Supplier

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"


async def _seed_product(db_session: AsyncSession) -> uuid.UUID:
    sup = Supplier(name="Forn", document="11222333000181")
    db_session.add(sup)
    await db_session.flush()
    prod = Product(sku="P-RBAC", name="Produto", supplier_id=sup.id, quantity=0, min_stock=0)
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(prod)
    return prod.id


async def _seed_open_alert(db_session: AsyncSession, product_id: uuid.UUID) -> uuid.UUID:
    alert = StockAlert(
        product_id=product_id,
        status=AlertStatus.OPEN,
        triggered_quantity=0,
        min_stock_at_trigger=5,
    )
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    return alert.id


async def test_me_returns_permissions(operator_client: AsyncClient) -> None:
    resp = await operator_client.get(f"{PREFIX}/auth/me")
    assert resp.status_code == 200, resp.text
    perms = resp.json()["permissions"]
    assert "movement:create" in perms
    assert "product:write" not in perms


async def test_operator_cannot_create_product(operator_client: AsyncClient) -> None:
    resp = await operator_client.post(
        f"{PREFIX}/products",
        json={"sku": "X1", "name": "Nope", "supplier_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    body = resp.json()["error"]
    assert body["code"] == "authorization_error"
    assert "product:write" in body["details"]["required"]


async def test_operator_can_create_movement(
    operator_client: AsyncClient, db_session: AsyncSession
) -> None:
    pid = await _seed_product(db_session)
    resp = await operator_client.post(
        f"{PREFIX}/movements",
        json={"product_id": str(pid), "type": "in", "quantity": 5},
    )
    assert resp.status_code == 201, resp.text


async def test_operator_acknowledge_but_not_resolve(
    operator_client: AsyncClient, db_session: AsyncSession
) -> None:
    pid = await _seed_product(db_session)
    aid = await _seed_open_alert(db_session, pid)

    ack = await operator_client.post(f"{PREFIX}/alerts/{aid}/acknowledge")
    assert ack.status_code == 200, ack.text

    res = await operator_client.post(f"{PREFIX}/alerts/{aid}/resolve")
    assert res.status_code == 403


async def test_manager_can_create_product(
    manager_client: AsyncClient, db_session: AsyncSession
) -> None:
    sup = Supplier(name="Forn", document="11222333000181")
    db_session.add(sup)
    await db_session.commit()
    await db_session.refresh(sup)
    resp = await manager_client.post(
        f"{PREFIX}/products",
        json={"sku": "M1", "name": "Prod Manager", "supplier_id": str(sup.id)},
    )
    assert resp.status_code == 201, resp.text


async def test_manager_cannot_manage_users(manager_client: AsyncClient) -> None:
    resp = await manager_client.post(
        f"{PREFIX}/users",
        json={"email": "n@test.com", "password": "Pw@123456", "full_name": "N"},
    )
    assert resp.status_code == 403


async def test_admin_can_manage_users(auth_client: AsyncClient) -> None:
    resp = await auth_client.post(
        f"{PREFIX}/users",
        json={"email": "novo@test.com", "password": "Pw@123456", "full_name": "Novo User"},
    )
    assert resp.status_code == 201, resp.text
```

- [ ] **Step 2: Rodar — deve passar**

TESTRUN `pytest tests/integration/test_rbac.py -q`
Expected: PASS (7 passed).

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_rbac.py
git commit -m "test(rbac): integração de autorização granular"
```

---

## Task 7: Verificação final + docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar README**

No `README.md`:
- Em Funcionalidades/Fase 1, ou numa nota, mencionar "RBAC granular por permissões nomeadas".
- No roadmap, marcar a Fase 2 como concluída:
```markdown
- [x] **Fase 2**: alertas de estoque baixo · dashboard operacional · RBAC granular
```

- [ ] **Step 2: Rodar todos os gates**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: ruff All checks passed, mypy Success, pytest todos verdes (33 anteriores + 4 unit + 7 integração RBAC).

- [ ] **Step 3: Validar end-to-end**

```bash
docker exec stockguardian-db-1 psql -U stockguardian -d stockguardian -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null 2>&1
docker compose -f docker/docker-compose.yml up -d --build api
sleep 7
docker compose -f docker/docker-compose.yml exec -T api python -m scripts.seed >/dev/null 2>&1
TOK=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@stockguardian.com","password":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOK"
```
Expected: JSON de `/auth/me` inclui `permissions` com todas as permissões (admin).

- [ ] **Step 4: Commit + push**
```bash
git add README.md
git commit -m "docs(rbac): RBAC granular no README + Fase 2 concluída"
git push -u origin feat/rbac-granular
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** módulo Permission + mapa + helpers (T1), require_permission
  (T2), UserMe + /auth/me (T3), migração de todas as rotas + remoção de require_role
  (T4), fixtures por role (T5), testes de integração incl. 403 com `details.required`
  (T6), gates+README+e2e (T7). ✔
- **Placeholders:** nenhum — todo passo tem código/comando.
- **Consistência de tipos:** `Permission`/`permissions_for`/`has_permissions` (T1)
  usados em T2/T3/T6; `require_permission` (T2) usado em T4; `UserMe` (T3) usado no
  /auth/me; fixtures `operator_client`/`manager_client` (T5) usadas em T6. ✔
- **Nota:** leituras (`*:read`) seguem exigindo só autenticação (sem guard de
  permissão) — todas as roles as têm; as permissões de leitura existem para o
  modelo e para o /auth/me, sem mudar comportamento.
