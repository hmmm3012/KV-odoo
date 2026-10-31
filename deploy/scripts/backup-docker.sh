#!/usr/bin/env bash
# Backup Docker Odoo stack: PostgreSQL dump + optional filestore.
#
# Usage:
#   ./deploy/scripts/backup-docker.sh                  # DB + filestore (default)
#   ./deploy/scripts/backup-docker.sh --no-filestore   # DB only
#   ./deploy/scripts/backup-docker.sh --with-filestore # explicit full backup
#   ./deploy/scripts/backup-docker.sh -d mydb          # named database
#
# Environment:
#   DB_NAME           database to dump (default: odoo)
#   SKIP_FILESTORE=1  same as --no-filestore
#   COMPOSE_FILES     e.g. "-f docker-compose.yml -f docker-compose.prod.yml"
#   BACKUP_DIR        output root (default: deploy/backup)
#   KEEP_DAYS         delete docker-* backups older than N days (default: 7; 0 = keep all)
#
# Output:
#   deploy/backup/docker-YYYY-MM-DD_HHMMSS/
#     odoo.dump           custom-format pg_dump
#     filestore.tar.gz    only when filestore is included
#     MANIFEST.txt        metadata
#   Also updates deploy/backup/docker-latest.dump (and filestore if present)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml}"
DB_NAME="${DB_NAME:-odoo}"
INCLUDE_FILESTORE=1
BACKUP_ROOT="${BACKUP_DIR:-${DEPLOY_DIR}/backup}"
KEEP_DAYS="${KEEP_DAYS:-7}"

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-filestore|-n)
      INCLUDE_FILESTORE=0
      shift
      ;;
    --with-filestore|-f)
      INCLUDE_FILESTORE=1
      shift
      ;;
    --db|-d)
      DB_NAME="${2:?--db requires a database name}"
      shift 2
      ;;
    --help|-h)
      usage 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
done

if [[ "${SKIP_FILESTORE:-0}" == "1" ]]; then
  INCLUDE_FILESTORE=0
fi

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

# Ensure db is reachable
if ! docker compose ${COMPOSE_FILES} exec -T db pg_isready -U "${POSTGRES_USER}" -d postgres >/dev/null 2>&1; then
  echo "==> Starting db service..."
  docker compose ${COMPOSE_FILES} up -d db
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
fi

if ! docker compose ${COMPOSE_FILES} exec -T db \
  psql -U "${POSTGRES_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1; then
  echo "Database '${DB_NAME}' does not exist in the container." >&2
  exit 1
fi

STAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT_DIR="${BACKUP_ROOT}/docker-${STAMP}"
mkdir -p "${OUT_DIR}"

DUMP_FILE="${OUT_DIR}/${DB_NAME}.dump"
LATEST_DUMP="${BACKUP_ROOT}/docker-latest.dump"

echo "==> Dumping database '${DB_NAME}'..."
docker compose ${COMPOSE_FILES} exec -T db \
  pg_dump -U "${POSTGRES_USER}" -Fc --no-owner --no-acl "${DB_NAME}" \
  > "${DUMP_FILE}"
cp -f "${DUMP_FILE}" "${LATEST_DUMP}"
DUMP_SIZE="$(du -h "${DUMP_FILE}" | cut -f1)"
echo "    ${DUMP_FILE} (${DUMP_SIZE})"

FILESTORE_LINE="skipped"
if [[ "${INCLUDE_FILESTORE}" -eq 1 ]]; then
  PROJECT_NAME="$(docker compose ${COMPOSE_FILES} config --format json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name","kv-odoo"))' 2>/dev/null \
    || true)"
  PROJECT_NAME="${PROJECT_NAME:-kv-odoo}"
  WEB_VOLUME="${PROJECT_NAME}_odoo-web-data"

  if ! docker volume inspect "${WEB_VOLUME}" >/dev/null 2>&1; then
    echo "Volume ${WEB_VOLUME} not found; cannot backup filestore." >&2
    exit 1
  fi

  FILESTORE_TGZ="${OUT_DIR}/filestore.tar.gz"
  LATEST_FS="${BACKUP_ROOT}/docker-latest-filestore.tar.gz"
  echo "==> Archiving filestore from volume ${WEB_VOLUME}..."
  docker run --rm \
    -v "${WEB_VOLUME}:/data:ro" \
    -v "${OUT_DIR}:/backup" \
    alpine:3.20 \
    tar czf /backup/filestore.tar.gz -C /data .
  cp -f "${FILESTORE_TGZ}" "${LATEST_FS}"
  FS_SIZE="$(du -h "${FILESTORE_TGZ}" | cut -f1)"
  FILESTORE_LINE="filestore.tar.gz (${FS_SIZE})"
  echo "    ${FILESTORE_TGZ} (${FS_SIZE})"
fi

{
  echo "stamp=${STAMP}"
  echo "database=${DB_NAME}"
  echo "dump=${DB_NAME}.dump"
  echo "dump_size=${DUMP_SIZE}"
  echo "filestore=${FILESTORE_LINE}"
  echo "postgres_user=${POSTGRES_USER}"
  echo "host=$(hostname -f 2>/dev/null || hostname)"
  echo "created_at=$(date -Iseconds)"
} > "${OUT_DIR}/MANIFEST.txt"

if [[ "${KEEP_DAYS}" =~ ^[0-9]+$ ]] && [[ "${KEEP_DAYS}" -gt 0 ]]; then
  echo "==> Pruning backups older than ${KEEP_DAYS} day(s)..."
  find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -name 'docker-*' -mtime "+${KEEP_DAYS}" -print -exec rm -rf {} +
fi

echo ""
echo "Backup complete: ${OUT_DIR}"
echo "  DB dump:   ${DUMP_FILE} (${DUMP_SIZE})"
echo "  Filestore: ${FILESTORE_LINE}"
echo "  Latest DB: ${LATEST_DUMP}"
if [[ "${INCLUDE_FILESTORE}" -eq 1 ]]; then
  echo "  Latest FS: ${BACKUP_ROOT}/docker-latest-filestore.tar.gz"
fi
