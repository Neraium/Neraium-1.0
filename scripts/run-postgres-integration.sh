#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
CONTAINER_NAME="neraium-postgres-integration-${RANDOM}-$$"
IMAGE_NAME="neraium-postgres-integration:${RANDOM}-$$"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker image rm -f "$IMAGE_NAME" >/dev/null 2>&1 || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for the PostgreSQL integration suite." >&2
  exit 1
fi

openssl req -x509 -newkey rsa:2048 -nodes   -keyout "$TMP_DIR/server.key"   -out "$TMP_DIR/server.crt"   -days 1 -subj "/CN=localhost" >/dev/null 2>&1

cat > "$TMP_DIR/Dockerfile" <<'EOF'
FROM postgres:16-alpine
COPY server.crt server.key /var/lib/postgresql/certs/
RUN chown postgres:postgres /var/lib/postgresql/certs/server.*     && chmod 600 /var/lib/postgresql/certs/server.key     && chmod 644 /var/lib/postgresql/certs/server.crt
EOF

docker build -q -t "$IMAGE_NAME" "$TMP_DIR" >/dev/null
docker run -d --name "$CONTAINER_NAME"   -e POSTGRES_USER=postgres   -e POSTGRES_PASSWORD=postgres   -e POSTGRES_DB=neraium   -p 127.0.0.1::5432   "$IMAGE_NAME"   -c ssl=on   -c ssl_cert_file=/var/lib/postgresql/certs/server.crt   -c ssl_key_file=/var/lib/postgresql/certs/server.key >/dev/null

for _ in $(seq 1 60); do
  if docker exec "$CONTAINER_NAME" pg_isready -h 127.0.0.1 -U postgres -d neraium >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! docker exec "$CONTAINER_NAME" pg_isready -h 127.0.0.1 -U postgres -d neraium >/dev/null 2>&1; then
  docker logs "$CONTAINER_NAME" >&2
  exit 1
fi

HOST_PORT="$(docker port "$CONTAINER_NAME" 5432/tcp | awk -F: 'NR==1 {print $NF}')"
export NERAIUM_TEST_POSTGRES_DSN="postgresql://postgres:postgres@127.0.0.1:${HOST_PORT}/neraium"
export PYTHONPATH="$ROOT_DIR/backend${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT_DIR"
python -m pytest tests/integration/test_database_connector_postgres.py -m integration "$@"
