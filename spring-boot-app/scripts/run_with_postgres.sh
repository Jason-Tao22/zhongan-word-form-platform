#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

"${SCRIPT_DIR}/start_local_postgres.sh"

export DB_URL="${DB_URL:-jdbc:postgresql://127.0.0.1:5432/zhongan_forms}"
export DB_DRIVER="${DB_DRIVER:-org.postgresql.Driver}"
export DB_USERNAME="${DB_USERNAME:-zhongan}"
export DB_PASSWORD="${DB_PASSWORD:-zhongan_pw}"

cd "${APP_DIR}"
exec mvn spring-boot:run
