# 📦 StockGuardian

Plataforma inteligente de **gestão e análise de estoque** — back-end pensado como
software real de empresa, com arquitetura limpa, segurança e testes.

> Projeto de portfólio demonstrando práticas modernas de back-end Python:
> Clean Architecture, Repository + Service Layer, autenticação JWT, async I/O,
> Docker e CI.

![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x%20async-red)
![Tests](https://img.shields.io/badge/tests-pytest-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## ✨ Funcionalidades (Fase 1 — MVP)

- 🔐 **Autenticação JWT** (access + refresh com rotação e revogação via Redis)
- 👥 **Usuários e papéis** (ADMIN / MANAGER / OPERATOR) com RBAC granular por permissões nomeadas (`product:write`, `alert:resolve`…); `/auth/me` expõe as permissões
- 🏭 **Fornecedores** — CRUD com validação de CPF/CNPJ
- 📦 **Produtos** — CRUD com SKU único, preço, estoque mín/máx
- 🔄 **Movimentações de estoque** — entrada / saída / ajuste, atômicas e com lock
- 📜 **Histórico** de movimentações com filtros (produto, tipo, período) e paginação
- 🩺 Health check, logging estruturado e respostas de erro padronizadas

## 🧱 Stack

| Camada | Tecnologia |
|--------|-----------|
| Linguagem | Python 3.13 |
| API | FastAPI |
| ORM | SQLAlchemy 2.x (async / asyncpg) |
| Migrations | Alembic |
| Banco | PostgreSQL 16 |
| Cache / tokens | Redis 7 |
| Validação | Pydantic v2 |
| Testes | pytest + pytest-asyncio |
| Deps | uv |
| Qualidade | ruff + mypy (strict) |
| Container | Docker + Docker Compose |
| CI | GitHub Actions |

## 🏗️ Arquitetura

Camadas com dependência apontando para dentro (Clean Architecture + DDD simplificado):

```
rotas → services (regra de negócio) → repositories (SQL) → models
```

Detalhes e diagrama: [`docs/architecture.md`](docs/architecture.md).

```
app/
├── api/            # rotas FastAPI (finas)
├── core/           # config, logging, security, db, redis
├── models/         # entidades SQLAlchemy
├── schemas/        # contratos Pydantic
├── repositories/   # Repository Pattern (acesso a dados)
├── services/       # Service Layer (regra de negócio)
├── dependencies/   # injeção (db, auth, redis)
├── exceptions/     # erros de domínio + handlers
├── middleware/     # correlation-id + request logging
└── utils/          # paginação
```

## 🚀 Como rodar (Docker-first)

Pré-requisitos: Docker + Docker Compose.

```bash
# 1. Configurar variáveis de ambiente
cp .env.example .env
# (opcional) gerar SECRET_KEY forte:
#   openssl rand -hex 32  → cole em SECRET_KEY no .env

# 2. Subir API + PostgreSQL + Redis (migrations rodam no start)
docker compose -f docker/docker-compose.yml up --build

# 3. Popular dados de demonstração (admin + produtos)
docker compose -f docker/docker-compose.yml exec api python -m scripts.seed
```

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Login inicial (do `.env`): `admin@stockguardian.com` / `Admin@123`.

## 🔌 Endpoints principais (prefixo `/api/v1`)

| Método | Rota | Descrição | Acesso |
|--------|------|-----------|--------|
| POST | `/auth/register` | Cadastro de usuário | público |
| POST | `/auth/login` | Login (retorna access + refresh) | público |
| POST | `/auth/refresh` | Renova tokens | público |
| POST | `/auth/logout` | Revoga refresh token | público |
| GET | `/auth/me` | Usuário autenticado | autenticado |
| GET/POST/PATCH/DELETE | `/users` | Gestão de usuários | ADMIN |
| GET/POST/PATCH/DELETE | `/suppliers` | Fornecedores | leitura: autenticado · escrita: MANAGER+ |
| GET/POST/PATCH/DELETE | `/products` | Produtos | leitura: autenticado · escrita: MANAGER+ |
| POST | `/movements` | Registrar movimentação | OPERATOR+ |
| GET | `/movements` | Histórico (filtros + paginação) | autenticado |
| GET | `/alerts` | Alertas de estoque baixo (filtro `status`, `product_id`) | autenticado |
| POST | `/alerts/{id}/acknowledge` | Reconhecer alerta | OPERATOR+ |
| POST | `/alerts/{id}/resolve` | Resolver alerta | MANAGER+ |
| GET | `/dashboard/summary` | Contadores gerais (cache Redis) | MANAGER+ |

## 🧪 Testes & qualidade

Testes de integração usam um **PostgreSQL real**; o Redis é substituído por
`fakeredis`. Defina `TEST_DATABASE_URL` (default: `...localhost:5432/stockguardian_test`).

```bash
# com um Postgres de teste disponível (ex.: docker compose up db)
uv pip install ".[dev]"
createdb stockguardian_test          # ou via psql

pytest                                # unit + integration
ruff check . && ruff format --check . # lint
mypy app                              # type-check (strict)
```

CI (GitHub Actions) roda lint + mypy + pytest contra um serviço Postgres a cada push/PR.

## 🗺️ Roadmap

- [x] **Fase 1 — MVP**: auth, usuários, fornecedores, produtos, movimentações, histórico
- [x] **Fase 2**: alertas de estoque baixo · dashboard operacional · RBAC granular
- [ ] **Fase 3**: detecção de superestoque, relatórios, export Excel, tarefas assíncronas
- [ ] **Fase 4**: observabilidade (Prometheus/OpenTelemetry), deploy, monitoramento

## 📄 Licença

MIT.
