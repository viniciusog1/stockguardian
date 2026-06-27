# Manifests Kubernetes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Manifests Kubernetes (Kustomize) para subir api + worker + Postgres +
Redis, com ConfigMap/Secret, migrations via Job e probes em /health e
/health/ready. Sem código de app.

**Architecture:** diretório `k8s/` agregado por `kustomization.yaml`; api/worker
como Deployments; Postgres/Redis in-cluster; Job de migração.

**Tech Stack:** Kubernetes, Kustomize.

Spec: `docs/superpowers/specs/2026-06-26-k8s-manifests-design.md`.

---

## Convenção de testes (ambiente)

Sem cluster local. Validação: parse YAML (multi-doc) + checagem dos recursos do
kustomization; gates do app seguem verdes (inalterado). Apply real no cluster do
dev (kind/minikube).

---

## Task 1: Base — namespace, config, secret, Postgres, Redis

**Files:**
- Create: `k8s/namespace.yaml`
- Create: `k8s/configmap.yaml`
- Create: `k8s/secret.example.yaml`
- Create: `k8s/postgres.yaml`
- Create: `k8s/redis.yaml`

- [ ] **Step 1: namespace.yaml**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: stockguardian
```

- [ ] **Step 2: configmap.yaml** — `stockguardian-config` com as variáveis não
  sensíveis (PROJECT_NAME, ENVIRONMENT=production, API_V1_PREFIX, LOG_LEVEL,
  LOG_JSON, DASHBOARD_CACHE_TTL, REPORT_JOB_RESULT_TTL, METRICS_ENABLED=true,
  TRACING_ENABLED=false, OTEL_EXPORTER_OTLP_ENDPOINT, POSTGRES_HOST=postgres,
  POSTGRES_PORT, POSTGRES_DB, REDIS_HOST=redis, REDIS_PORT, REDIS_DB).

- [ ] **Step 3: secret.example.yaml** — `stockguardian-secrets` (`stringData`)
  com placeholders: `SECRET_KEY`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `FIRST_SUPERUSER_EMAIL`, `FIRST_SUPERUSER_PASSWORD`. Comentar que é exemplo.

- [ ] **Step 4: postgres.yaml** — Deployment `postgres` (image `postgres:16-alpine`,
  env `POSTGRES_USER/PASSWORD/DB` do secret/config, volumeMount em
  `/var/lib/postgresql/data`), PVC `postgres-data` (1Gi), Service `postgres` (5432).
  readiness: `pg_isready`.

- [ ] **Step 5: redis.yaml** — Deployment `redis` (image `redis:7-alpine`,
  `--appendonly yes`), Service `redis` (6379). readiness: `redis-cli ping`.

- [ ] **Step 6: Validar YAML**

TESTRUN `python -c "import yaml,glob; [list(yaml.safe_load_all(open(f,encoding='utf-8'))) for f in glob.glob('k8s/*.yaml')]; print('yaml ok')"`

- [ ] **Step 7: Commit**
```bash
git add k8s/namespace.yaml k8s/configmap.yaml k8s/secret.example.yaml k8s/postgres.yaml k8s/redis.yaml
git commit -m "feat(k8s): namespace, config/secret e Postgres/Redis"
```

---

## Task 2: App — migrate Job, api, worker, kustomization

**Files:**
- Create: `k8s/migrate-job.yaml`
- Create: `k8s/api.yaml`
- Create: `k8s/worker.yaml`
- Create: `k8s/kustomization.yaml`

- [ ] **Step 1: migrate-job.yaml** — Job `stockguardian-migrate` (image da app,
  `command: ["alembic","upgrade","head"]`, `restartPolicy: Never`,
  `backoffLimit: 3`, `envFrom` config+secret).

- [ ] **Step 2: api.yaml** — Deployment `api` (replicas 2, image da app,
  `command: ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`,
  containerPort 8000, `envFrom` config+secret, liveness `/health`, readiness
  `/health/ready`, resources requests/limits) + Service `api` (ClusterIP, 80→8000).

```yaml
        livenessProbe:
          httpGet: { path: /health, port: 8000 }
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet: { path: /health/ready, port: 8000 }
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests: { cpu: "100m", memory: "256Mi" }
          limits: { cpu: "500m", memory: "512Mi" }
```

- [ ] **Step 3: worker.yaml** — Deployment `worker` (replicas 1, image da app,
  `command: ["arq","app.worker.settings.WorkerSettings"]`, `envFrom` config+secret,
  resources). Sem probes HTTP (processo não-HTTP).

- [ ] **Step 4: kustomization.yaml**
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: stockguardian
resources:
  - namespace.yaml
  - configmap.yaml
  - secret.example.yaml
  - postgres.yaml
  - redis.yaml
  - migrate-job.yaml
  - api.yaml
  - worker.yaml
images:
  - name: ghcr.io/viniciusog1/stockguardian
    newTag: latest
```

- [ ] **Step 5: Validar YAML + referências do kustomization**

TESTRUN `python -c "import yaml,glob; [list(yaml.safe_load_all(open(f,encoding='utf-8'))) for f in glob.glob('k8s/*.yaml')]; print('yaml ok')"`
TESTRUN `python -c "import yaml; k=yaml.safe_load(open('k8s/kustomization.yaml',encoding='utf-8')); import os; miss=[r for r in k['resources'] if not os.path.exists('k8s/'+r)]; print('faltando:', miss or 'nenhum')"`
Expected: `yaml ok` + `faltando: nenhum`.

- [ ] **Step 6: Commit**
```bash
git add k8s/migrate-job.yaml k8s/api.yaml k8s/worker.yaml k8s/kustomization.yaml
git commit -m "feat(k8s): migrate Job, api e worker Deployments + kustomization"
```

---

## Task 3: README do k8s + raiz + gates

**Files:**
- Create: `k8s/README.md`
- Modify: `README.md`

- [ ] **Step 1: k8s/README.md** — passo-a-passo:
  - build da imagem (`docker build -f docker/Dockerfile -t ghcr.io/viniciusog1/stockguardian:latest .`) e load no cluster (kind/minikube) ou push;
  - criar o Secret real a partir de `secret.example.yaml` (não versionar o real);
  - `kubectl apply -k k8s/`;
  - aguardar o Job de migração (`kubectl wait --for=condition=complete job/stockguardian-migrate -n stockguardian`);
  - `kubectl port-forward svc/api 8000:80 -n stockguardian` → `/health` e `/health/ready`.

- [ ] **Step 2: README raiz**
  - seção curta "Deploy (Kubernetes)" apontando para `k8s/` e o `k8s/README.md`;
  - roadmap:
```markdown
- [x] **Fase 4**: métricas · health/readiness · scrape (Prometheus+Grafana) · tracing OTel · deploy (manifests Kubernetes)
```

- [ ] **Step 3: Gates (app inalterado)**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: tudo verde.

- [ ] **Step 4: Validação no cluster (dev, opcional)**
```bash
# kind create cluster && docker build ... && kind load docker-image ...
kubectl apply -k k8s/
kubectl wait --for=condition=complete job/stockguardian-migrate -n stockguardian --timeout=120s
kubectl get pods -n stockguardian
kubectl port-forward svc/api 8000:80 -n stockguardian &
curl -s localhost:8000/health; curl -s localhost:8000/health/ready
```

- [ ] **Step 5: Commit + push**
```bash
git add k8s/README.md README.md
git commit -m "docs(k8s): guia de deploy + Fase 4 concluída"
git push -u origin feat/k8s-manifests
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** base (ns/config/secret/postgres/redis) (T1), app
  (migrate Job/api/worker/kustomization) (T2), READMEs + gates (T3). ✔
- **Placeholders:** apenas no `secret.example.yaml` (intencional, documentado).
- **Consistência:** `POSTGRES_HOST=postgres`/`REDIS_HOST=redis` == nomes dos
  Services; probes usam `/health` e `/health/ready`; api `command: uvicorn`
  (ignora migrations do entrypoint), migrations no Job; imagem única referenciada
  no `kustomization.images`.
- **Sem código de app / sem migration / gates inalterados.**
- **Notas:** Postgres/Redis in-cluster são para demo (trocar por gerenciados em
  prod); ordem recomendada: Job de migração antes do tráfego (README).
