# Stack de Scrape (Prometheus + Grafana) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir Prometheus (scrape do `/metrics`) e Grafana (datasource +
dashboard provisionados) no docker-compose, num profile `observability` opt-in.
**Sem código de app**, sem migration.

**Architecture:** arquivos de config em `docker/prometheus` e `docker/grafana`;
dois serviços novos no compose (profile `observability`). Dashboard usa os nomes
de métricas já verificados.

**Tech Stack:** Prometheus, Grafana, Docker Compose.

Spec: `docs/superpowers/specs/2026-06-26-observability-stack-design.md`.

---

## Convenção de testes (ambiente)

Sem testes automatizados (infra). Validação local: parsear JSON/YAML + manter
`ruff`/`mypy`/`pytest` verdes (app inalterado). Validação real no Docker do dev.

---

## Task 1: Configs do Prometheus e Grafana

**Files:**
- Create: `docker/prometheus/prometheus.yml`
- Create: `docker/grafana/provisioning/datasources/datasource.yml`
- Create: `docker/grafana/provisioning/dashboards/provider.yml`
- Create: `docker/grafana/dashboards/stockguardian.json`

- [ ] **Step 1: prometheus.yml**
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: stockguardian-api
    metrics_path: /metrics
    static_configs:
      - targets: ["api:8000"]
```

- [ ] **Step 2: datasource Grafana**

`docker/grafana/provisioning/datasources/datasource.yml`:
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    uid: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

- [ ] **Step 3: provider de dashboards**

`docker/grafana/provisioning/dashboards/provider.yml`:
```yaml
apiVersion: 1
providers:
  - name: stockguardian
    type: file
    disableDeletion: false
    allowUiUpdates: true
    options:
      path: /etc/dashboards
      foldersFromFilesStructure: false
```

- [ ] **Step 4: dashboard JSON**

`docker/grafana/dashboards/stockguardian.json` — dashboard com 5 painéis
(timeseries), todos com `datasource: {type: prometheus, uid: prometheus}`:
- Request rate: `sum by (handler) (rate(http_requests_total[5m]))`
- Latência p95: `histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket[5m])))`
- Movimentações/min por tipo: `sum by (type) (rate(stockguardian_movements_total[5m]))`
- Alertas (abertos/resolvidos): `sum by (kind) (rate(stockguardian_alerts_opened_total[5m]))` e `..._resolved_total`
- Jobs enfileirados: `sum by (report) (rate(stockguardian_report_jobs_enqueued_total[5m]))`

(JSON completo escrito no arquivo; `schemaVersion` recente, `title: "StockGuardian"`.)

- [ ] **Step 5: Validar sintaxe local**

TESTRUN `python -c "import json; json.load(open('docker/grafana/dashboards/stockguardian.json')); print('json ok')"`
TESTRUN (se houver pyyaml) `python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('docker/**/*.yml', recursive=True)]; print('yaml ok')"`
Expected: `json ok` (+ `yaml ok` se pyyaml disponível).

- [ ] **Step 6: Commit**
```bash
git add docker/prometheus docker/grafana
git commit -m "feat(observability): configs Prometheus + provisioning Grafana + dashboard"
```

---

## Task 2: Serviços no docker-compose + env

**Files:**
- Modify: `docker/docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Serviços prometheus + grafana (profile observability)**

Em `docker/docker-compose.yml`, antes de `volumes:`:
```yaml
  prometheus:
    image: prom/prometheus:latest
    profiles: ["observability"]
    volumes:
      - ../docker/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - promdata:/prometheus
    ports:
      - "9090:9090"
    depends_on:
      - api
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    profiles: ["observability"]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - ../docker/grafana/provisioning:/etc/grafana/provisioning:ro
      - ../docker/grafana/dashboards:/etc/dashboards:ro
      - grafanadata:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    restart: unless-stopped
```
E no bloco `volumes:` ao final, adicionar:
```yaml
  promdata:
  grafanadata:
```

- [ ] **Step 2: .env.example**

Na seção Aplicação (ou nova seção Observabilidade):
```
# ---- Observabilidade ----
GRAFANA_ADMIN_PASSWORD=admin
```

- [ ] **Step 3: Validar YAML do compose**

TESTRUN (se pyyaml) `python -c "import yaml; d=yaml.safe_load(open('docker/docker-compose.yml')); print(sorted(d['services']))"`
Expected: inclui `api, db, grafana, prometheus, redis, worker`.

- [ ] **Step 4: Commit**
```bash
git add docker/docker-compose.yml .env.example
git commit -m "feat(observability): serviços prometheus + grafana (profile observability)"
```

---

## Task 3: README + gates finais

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README — seção de observabilidade**

Acrescentar (perto de "Como rodar" ou numa subseção própria):
```markdown
### 📈 Observabilidade (opcional)

Sobe Prometheus + Grafana (profile `observability`):

\`\`\`bash
docker compose -f docker/docker-compose.yml --profile observability up -d --build
\`\`\`

- Prometheus: <http://localhost:9090> (Status ▸ Targets: `stockguardian-api` UP)
- Grafana: <http://localhost:3000> — login `admin` / `${GRAFANA_ADMIN_PASSWORD:-admin}`;
  dashboard "StockGuardian" já provisionado.
```
E no roadmap:
```markdown
- [ ] **Fase 4**: ~~métricas Prometheus~~ ✅ · ~~health/readiness~~ ✅ · ~~scrape (Prometheus+Grafana)~~ ✅ · tracing OTel · deploy
```

- [ ] **Step 2: Gates (app inalterado, mas confirmar verde)**

TESTRUN `ruff check . && ruff format --check . && mypy app && pytest -q`
Expected: tudo verde.

- [ ] **Step 3: Validação no Docker (dev)**

```bash
docker compose -f docker/docker-compose.yml --profile observability up -d --build
# Prometheus target UP:
curl -s localhost:9090/api/v1/targets | grep stockguardian-api
# Grafana responde:
curl -s -o /dev/null -w "%{http_code}\n" localhost:3000/login   # 200
```

- [ ] **Step 4: Commit + push**
```bash
git add README.md
git commit -m "docs(observability): stack Prometheus+Grafana + Fase 4 atualizada"
git push -u origin feat/observability-stack
```
Abrir PR pela URL retornada.

---

## Self-review

- **Cobertura do spec:** configs prometheus+grafana+dashboard (T1), serviços no
  compose com profile + env (T2), README+gates (T3). ✔
- **Placeholders:** nenhum (JSON do dashboard completo no arquivo).
- **Consistência:** datasource uid `prometheus` referenciado pelos painéis do
  dashboard; scrape target `api:8000` == serviço/porta do compose; profile
  `observability` nos dois serviços; volumes `promdata`/`grafanadata` declarados.
- **Sem código de app / sem migration / gates inalterados.**
- **Nota:** caminho de provisioning do Grafana = `/etc/grafana/provisioning`;
  dashboards JSON em `/etc/dashboards` (provider aponta para lá). Stack é opt-in
  (profile) para não pesar o `up` padrão.
