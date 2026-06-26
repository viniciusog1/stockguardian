#!/usr/bin/env bash
# Entrypoint do container da API: aplica migrations e então executa o comando
# recebido (uvicorn por padrão). `depends_on: service_healthy` já garante que o
# Postgres está pronto antes deste ponto.
set -euo pipefail

echo "[entrypoint] aplicando migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] iniciando: $*"
exec "$@"
