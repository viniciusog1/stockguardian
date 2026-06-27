# Design — Manifests Kubernetes (Fase 4, iteração 5)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

Fatia final da Fase 4 (deploy). Entrega **manifests Kubernetes** para subir o
StockGuardian num cluster: API + worker (ARQ) + Postgres + Redis, com
configuração/segredos separados e **probes** usando os endpoints `/health`
(liveness) e `/health/ready` (readiness) construídos antes.

É **infra** (YAML) — **sem código de app** e sem migration. Branch parte de `main`.

## Decisões fechadas

- **Diretório `k8s/`** na raiz, agregado por **Kustomize** (`kustomization.yaml`).
- **Namespace dedicado** `stockguardian`.
- **Config x Secret separados:** `ConfigMap` (não sensível) + `Secret` de exemplo
  (`secret.example.yaml`, placeholders; o real não é versionado).
- **Migrations via Job** (`alembic upgrade head`) — desacopla do start da API
  (evita corrida entre réplicas). A API sobe com `command: uvicorn` (ignora o
  entrypoint que rodaria migrations).
- **API e worker em Deployments separados:** worker roda
  `arq app.worker.settings.WorkerSettings`.
- **Postgres e Redis incluídos** (Deployment + Service; Postgres com PVC) para os
  manifests serem aplicáveis fim-a-fim; em produção real, trocar por serviços
  gerenciados.
- **Probes:** liveness `GET /health`, readiness `GET /health/ready` na porta 8000.
- **Imagem:** `ghcr.io/viniciusog1/stockguardian:latest` (ajustável);
  `imagePullPolicy: IfNotPresent`.

## Recursos (arquivos em `k8s/`)

| Arquivo | Conteúdo |
|---------|----------|
| `namespace.yaml` | Namespace `stockguardian` |
| `configmap.yaml` | `stockguardian-config` (PROJECT_NAME, ENVIRONMENT, API_V1_PREFIX, LOG_*, *_TTL, METRICS_ENABLED, TRACING_ENABLED, OTEL endpoint, POSTGRES_HOST/PORT/DB, REDIS_HOST/PORT/DB) |
| `secret.example.yaml` | `stockguardian-secrets` (stringData: SECRET_KEY, POSTGRES_USER, POSTGRES_PASSWORD, FIRST_SUPERUSER_PASSWORD) — **placeholders** |
| `postgres.yaml` | Deployment + Service (`postgres:5432`) + PVC |
| `redis.yaml` | Deployment + Service (`redis:6379`) |
| `migrate-job.yaml` | Job `stockguardian-migrate` (`alembic upgrade head`) |
| `api.yaml` | Deployment (`command: uvicorn`, probes, envFrom config+secret, 2 réplicas) + Service `api` (ClusterIP 80→8000) |
| `worker.yaml` | Deployment (`command: arq ...`, envFrom config+secret, 1 réplica) |
| `kustomization.yaml` | agrega todos os recursos, `namespace: stockguardian` |
| `README.md` | passo-a-passo (build/push imagem, criar secret real, ordem de apply) |

## Detalhes

### Probes (api)
```yaml
livenessProbe:
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 10
  periodSeconds: 10
readinessProbe:
  httpGet: { path: /health/ready, port: 8000 }
  initialDelaySeconds: 5
  periodSeconds: 10
```

### Env
- API e worker: `envFrom: [configMapRef: stockguardian-config, secretRef: stockguardian-secrets]`.
- `POSTGRES_HOST=postgres`, `REDIS_HOST=redis` (nomes dos Services).
- `TRACING_ENABLED=false` por default (sem coletor no cluster nesta fatia).

### Migrations
- Job com a imagem da app e `command: ["alembic","upgrade","head"]`,
  `restartPolicy: Never`, `backoffLimit: 3`, `envFrom` igual à API.
- README orienta aplicar/esperar o Job antes (ou junto, ciente da corrida com a
  readiness que checa conexão, não schema).

### Recursos
- requests/limits modestos (ex.: api `100m/256Mi` → `500m/512Mi`).

## Testes / verificação

Sem testes automatizados (infra, sem cluster local aqui). Validação:
- **Local:** `yaml.safe_load_all` em todos os manifests (multi-doc válido);
  conferir que os recursos do `kustomization.yaml` existem; `ruff`/`mypy`/`pytest`
  seguem verdes (app inalterado).
- **Cluster (dev, kind/minikube):** build da imagem + load; criar Secret real a
  partir do exemplo; `kubectl apply -k k8s/`; Job de migração completa; pods
  `api`/`worker` Ready; `kubectl port-forward svc/api 8000:80` → `/health` 200 e
  `/health/ready` ready.

## Fora de escopo (futuro)

- Ingress/TLS, HorizontalPodAutoscaler, NetworkPolicies.
- Observabilidade no cluster (Prometheus Operator, ServiceMonitor, Jaeger).
- Pipeline de CD (build/push automatizado) — pode ser a próxima fatia.
- Helm chart (poderia substituir o Kustomize numa evolução).
