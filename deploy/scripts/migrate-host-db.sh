#!/usr/bin/env bash
# Import host PostgreSQL dump into the Docker stack (optional filestore copy).
#
# Prerequisites:
#   - deploy/.env configured
#   - DUMP_FILE set, or run backup-host-db.sh first (uses deploy/backup/host-odoo.dump)
#
# Usage:
#   SKIP_FILESTORE=1 ./deploy/scripts/migrate-host-db.sh
#   DUMP_FILE=deploy/backup/odoo-2026-01-01_120000.dump SKIP_FILESTORE=1 ./deploy/scripts/migrate-host-db.sh
#
# Environment:
#   DUMP_FILE         path to custom-format pg_dump (skip live pg_dump if set and file exists)
#   SKIP_FILESTORE=1  do not copy filestore (DB-only migration)
#   COMPOSE_FILES     e.g. "-f docker-compose.yml -f docker-compose.prod.yml"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml}"
LOCAL_DB_HOST="${LOCAL_DB_HOST:-localhost}"
LOCAL_DB_PORT="${LOCAL_DB_PORT:-5432}"
LOCAL_DB_USER="${LOCAL_DB_USER:-debian1}"
LOCAL_DB_NAME="${LOCAL_DB_NAME:-odoo}"
LOCAL_PGPASSWORD="${LOCAL_PGPASSWORD:-1}"
FILESTORE_SRC="${FILESTORE_SRC:-${HOME}/.local/share/Odoo/filestore/${LOCAL_DB_NAME}}"
SKIP_FILESTORE="${SKIP_FILESTORE:-0}"

DEFAULT_DUMP="${DEPLOY_DIR}/backup/host-${LOCAL_DB_NAME}.dump"
DUMP_FILE="${DUMP_FILE:-${DEFAULT_DUMP}}"

cd "${DEPLOY_DIR}"

if [[ ! -f .env ]]; then
  echo "Missing ${DEPLOY_DIR}/.env — copy from .env.example first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${POSTGRES_USER:?POSTGRES_USER not set in .env}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD not set in .env}"

mkdir -p "${DEPLOY_DIR}/backup"

if [[ ! -f "${DUMP_FILE}" ]]; then
  echo "==> No dump at ${DUMP_FILE}; dumping local database ${LOCAL_DB_NAME}..."
  PGPASSWORD="${LOCAL_PGPASSWORD}" pg_dump \
    -h "${LOCAL_DB_HOST}" -p "${LOCAL_DB_PORT}" -U "${LOCAL_DB_USER}" \
    -Fc --no-owner --no-acl \
    -f "${DUMP_FILE}" "${LOCAL_DB_NAME}"
else
  echo "==> Using existing dump: ${DUMP_FILE}"
fi

echo "==> Ensuring Docker services are up (db)..."
docker compose ${COMPOSE_FILES} up -d db
echo "==> Waiting for PostgreSQL to accept connections..."
for i in $(seq 1 60); do
  if docker compose ${COMPOSE_FILES} exec -T db pg_isready -U "${POSTGRES_USER}" -d postgres >/dev/null 2>&1; then
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    echo "PostgreSQL did not become ready in time." >&2
    exit 1
  fi
  sleep 2
done

echo "==> Recreating database ${LOCAL_DB_NAME} in container..."
docker compose ${COMPOSE_FILES} exec -T db psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${LOCAL_DB_NAME}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${LOCAL_DB_NAME}";
CREATE DATABASE "${LOCAL_DB_NAME}" OWNER "${POSTGRES_USER}" ENCODING 'UTF8' TEMPLATE template0;
SQL

echo "==> Restoring dump into container..."
docker compose ${COMPOSE_FILES} exec -T db pg_restore \
  -U "${POSTGRES_USER}" -d "${LOCAL_DB_NAME}" --no-owner --role="${POSTGRES_USER}" \
  < "${DUMP_FILE}"

PROJECT_NAME="$(docker compose ${COMPOSE_FILES} config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name","kv-odoo"))')"

if [[ "${SKIP_FILESTORE}" == "1" ]]; then
  echo "==> Skipping filestore (SKIP_FILESTORE=1)."
else
  if [[ ! -d "${FILESTORE_SRC}" ]]; then
    echo "WARNING: Filestore not found at ${FILESTORE_SRC} — attachments may be missing." >&2
  else
    echo "==> Copying filestore into odoo-web-data volume..."
    docker compose ${COMPOSE_FILES} stop odoo 2>/dev/null || true
    VOLUME="${PROJECT_NAME}_odoo-web-data"
    docker run --rm \
      -v "${VOLUME}:/data" \
      -v "${FILESTORE_SRC}:/src:ro" \
      alpine:3.20 \
      sh -c "mkdir -p /data/filestore/${LOCAL_DB_NAME} && cp -a /src/. /data/filestore/${LOCAL_DB_NAME}/"
  fi
fi

echo "==> Starting Odoo..."
docker compose ${COMPOSE_FILES} up -d odoo

cat <<EOF

Done.

- Database name in Docker: ${LOCAL_DB_NAME}
- Dump used: ${DUMP_FILE}
- Filestore: $(if [[ "${SKIP_FILESTORE}" == "1" ]]; then echo "not copied (run again without SKIP_FILESTORE=1 to sync attachments)"; else echo "/var/lib/odoo/filestore/${LOCAL_DB_NAME}"; fi)

Open Odoo and select database "${LOCAL_DB_NAME}".
Set ODOO_ADMIN_PASSWD in deploy/.env to match your old master password if needed.
EOF
