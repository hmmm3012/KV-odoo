#!/usr/bin/env bash
# Backup local Odoo PostgreSQL database only (no filestore).
#
# Usage:
#   ./deploy/scripts/backup-host-db.sh
#
# Output: deploy/backup/odoo-YYYY-MM-DD_HHMMSS.dump
# Also updates deploy/backup/host-odoo.dump (latest symlink target copy)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="${REPO_ROOT}/deploy"
BACKUP_DIR="${DEPLOY_DIR}/backup"

LOCAL_DB_HOST="${LOCAL_DB_HOST:-localhost}"
LOCAL_DB_PORT="${LOCAL_DB_PORT:-5432}"
LOCAL_DB_USER="${LOCAL_DB_USER:-debian1}"
LOCAL_DB_NAME="${LOCAL_DB_NAME:-odoo}"
LOCAL_PGPASSWORD="${LOCAL_PGPASSWORD:-1}"

STAMP="$(date +%Y-%m-%d_%H%M%S)"
DUMP_FILE="${BACKUP_DIR}/${LOCAL_DB_NAME}-${STAMP}.dump"
LATEST_COPY="${BACKUP_DIR}/host-${LOCAL_DB_NAME}.dump"

mkdir -p "${BACKUP_DIR}"

echo "==> Dumping ${LOCAL_DB_NAME} from ${LOCAL_DB_HOST}:${LOCAL_DB_PORT} (database only, no filestore)..."
PGPASSWORD="${LOCAL_PGPASSWORD}" pg_dump \
  -h "${LOCAL_DB_HOST}" -p "${LOCAL_DB_PORT}" -U "${LOCAL_DB_USER}" \
  -Fc --no-owner --no-acl \
  -f "${DUMP_FILE}" "${LOCAL_DB_NAME}"

cp -f "${DUMP_FILE}" "${LATEST_COPY}"

SIZE="$(du -h "${DUMP_FILE}" | cut -f1)"
echo ""
echo "Backup complete."
echo "  Timestamped: ${DUMP_FILE} (${SIZE})"
echo "  Latest copy: ${LATEST_COPY}"
echo ""
echo "Restore into Docker: DUMP_FILE=${DUMP_FILE} SKIP_FILESTORE=1 ./deploy/scripts/migrate-host-db.sh"
