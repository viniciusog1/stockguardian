# Deploy no Kubernetes

Manifests (Kustomize) para subir o StockGuardian: **api** + **worker** (ARQ) +
**Postgres** + **Redis**, com migrations via Job e probes em `/health`
(liveness) e `/health/ready` (readiness).

> Postgres e Redis aqui são para demonstração (single-replica). Em produção,
> prefira serviços gerenciados e remova-os do `kustomization.yaml`, ajustando
> `POSTGRES_HOST`/`REDIS_HOST` no ConfigMap.

## Pré-requisitos

- Um cluster (ex.: [kind](https://kind.sigs.k8s.io/) ou minikube) e `kubectl`.
- A imagem da aplicação acessível ao cluster.

## 1. Construir a imagem

```bash
docker build -f docker/Dockerfile -t ghcr.io/viniciusog1/stockguardian:latest .
```

- **kind:** `kind load docker-image ghcr.io/viniciusog1/stockguardian:latest`
- **minikube:** `minikube image load ghcr.io/viniciusog1/stockguardian:latest`
- **registry:** `docker push ghcr.io/viniciusog1/stockguardian:latest`

(Para outra tag/registry, ajuste `images:` no `kustomization.yaml`.)

## 2. Criar o Secret real

`secret.example.yaml` tem **placeholders**. Gere um Secret real (não versione):

```bash
cp k8s/secret.example.yaml /tmp/stockguardian-secret.yaml
# edite SECRET_KEY (openssl rand -hex 32), POSTGRES_PASSWORD, etc.
```

Para um deploy real, troque a referência no `kustomization.yaml` por esse arquivo
editado, ou aplique-o à parte com `kubectl apply -n stockguardian -f`.

## 3. Aplicar

```bash
kubectl apply -k k8s/
```

## 4. Aguardar as migrations e validar

```bash
kubectl wait --for=condition=complete job/stockguardian-migrate -n stockguardian --timeout=120s
kubectl get pods -n stockguardian

kubectl port-forward svc/api 8000:80 -n stockguardian
# em outro terminal:
curl -s localhost:8000/health          # {"status":"ok",...}
curl -s localhost:8000/health/ready    # {"ready":true,...}
```

> A API sobe com `command: uvicorn` (ignora o entrypoint que rodaria migrations);
> quem migra é o Job `stockguardian-migrate`. Aplique/aguarde o Job antes de
> direcionar tráfego de escrita.
