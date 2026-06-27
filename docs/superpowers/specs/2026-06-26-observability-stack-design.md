# Design — Stack de Scrape: Prometheus + Grafana (Fase 4, iteração 3)

**Data:** 2026-06-26
**Status:** Proposto
**Projeto:** StockGuardian

## Contexto

A iteração 1 da Fase 4 expôs `/metrics` (HTTP + métricas de negócio). Esta
iteração **fecha o ciclo de métricas**: sobe **Prometheus** (scrape do `/metrics`)
e **Grafana** (datasource + dashboard provisionados) no `docker-compose`, para
visualizar as métricas que já produzimos.

É uma fatia **de infraestrutura** — **sem código de aplicação** e sem migration.
O `/metrics` já existe; aqui só adicionamos coleta e visualização. Branch parte de
`main`.

## Decisões fechadas

- **Opt-in via profile:** Prometheus e Grafana ficam num profile `observability`
  do compose — o `docker compose up` padrão segue leve; `docker compose
  --profile observability up` sobe tudo. Mantém o core enxuto e demonstra o
  recurso de profiles.
- **Prometheus** raspa `api:8000/metrics` (DNS da rede do compose), job
  `stockguardian-api`, `scrape_interval: 15s`. Porta `9090`.
- **Grafana** com **provisionamento**: datasource Prometheus (uid fixo
  `prometheus`) + um dashboard carregado automaticamente. Porta `3000`. Senha do
  admin via `GF_SECURITY_ADMIN_PASSWORD` (default `admin`, configurável por
  `.env`).
- **Dashboard inicial** cobre HTTP (taxa de req, latência p95) e negócio
  (movimentações, alertas, jobs), usando os nomes reais já verificados.

## Métricas usadas no dashboard

HTTP (instrumentator):
- `http_requests_total{handler,method,status}`
- `http_request_duration_seconds_bucket{handler,le}` (p95 por handler)

Negócio (prometheus_client):
- `stockguardian_movements_total{type}`
- `stockguardian_alerts_opened_total{kind}` / `stockguardian_alerts_resolved_total{kind}`
- `stockguardian_report_jobs_enqueued_total{report}`

Painéis (timeseries):
1. **Request rate** — `sum by (handler) (rate(http_requests_total[5m]))`
2. **Latência p95** — `histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket[5m])))`
3. **Movimentações/min por tipo** — `sum by (type) (rate(stockguardian_movements_total[5m]))`
4. **Alertas abertos/resolvidos** — `sum by (kind) (rate(stockguardian_alerts_opened_total[5m]))` + resolved
5. **Jobs de relatório enfileirados** — `sum by (report) (rate(stockguardian_report_jobs_enqueued_total[5m]))`

## Arquivos

**Novos:**
- `docker/prometheus/prometheus.yml` — scrape config.
- `docker/grafana/provisioning/datasources/datasource.yml` — datasource Prometheus.
- `docker/grafana/provisioning/dashboards/provider.yml` — provider de dashboards.
- `docker/grafana/dashboards/stockguardian.json` — dashboard inicial.

**Editados:**
- `docker/docker-compose.yml` — serviços `prometheus` e `grafana` (profile
  `observability`, volumes de config, depends_on/ports).
- `.env.example` — `GRAFANA_ADMIN_PASSWORD=admin`.
- `README.md` — seção de observabilidade (como subir, portas, credenciais).

## Detalhes de config

`prometheus.yml`:
```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: stockguardian-api
    metrics_path: /metrics
    static_configs:
      - targets: ["api:8000"]
```

`docker-compose.yml` (trecho):
```yaml
  prometheus:
    image: prom/prometheus:latest
    profiles: ["observability"]
    volumes:
      - ../docker/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - promdata:/prometheus
    ports: ["9090:9090"]
    depends_on: [api]
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    profiles: ["observability"]
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - ../docker/grafana/provisioning:/etc/provisioning:ro
      - grafanadata:/var/lib/grafana
    ports: ["3000:3000"]
    depends_on: [prometheus]
    restart: unless-stopped
```
> O caminho de provisioning do Grafana é `/etc/grafana/provisioning`; o compose
> monta em `/etc/grafana/provisioning` (ajuste fechado na implementação) e o
> provider aponta os dashboards para o JSON montado.

## Testes / verificação

Sem testes automatizados (infra). Validação:
- **Local (sem Docker):** parsear `stockguardian.json` (JSON válido) e os YAMLs;
  `ruff`/`mypy`/`pytest` seguem verdes (app inalterado).
- **Docker (dev):**
  - `docker compose --profile observability up -d --build`.
  - Prometheus `http://localhost:9090` → Status ▸ Targets: `stockguardian-api` UP.
  - Grafana `http://localhost:3000` (admin / senha) → dashboard "StockGuardian"
    com os painéis populando após algumas requisições/movimentações.

## Fora de escopo (próximas iterações da Fase 4)

- Alertmanager + regras de alerta (thresholds).
- Tracing OpenTelemetry (Jaeger/Tempo).
- Métricas do worker ARQ (endpoint próprio do worker).
- Deploy/manifests de produção (Kubernetes).
