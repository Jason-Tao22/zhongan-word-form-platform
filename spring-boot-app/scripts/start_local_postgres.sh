#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-zhongan-postgres}"
POSTGRES_DB="${POSTGRES_DB:-zhongan_forms}"
POSTGRES_USER="${POSTGRES_USER:-zhongan}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-zhongan_pw}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not running" >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
  if ! docker ps --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
    docker start "${CONTAINER_NAME}" >/dev/null
  fi
else
  docker run -d \
    --name "${CONTAINER_NAME}" \
    -e POSTGRES_DB="${POSTGRES_DB}" \
    -e POSTGRES_USER="${POSTGRES_USER}" \
    -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
    -p "${POSTGRES_PORT}:5432" \
    "${POSTGRES_IMAGE}" >/dev/null
fi

for _ in $(seq 1 60); do
  if docker exec "${CONTAINER_NAME}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    echo "postgres ready: ${POSTGRES_USER}@127.0.0.1:${POSTGRES_PORT}/${POSTGRES_DB}"
    exit 0
  fi
  sleep 1
done

echo "postgres did not become ready in time" >&2
docker logs --tail 100 "${CONTAINER_NAME}" >&2 || true
exit 1
