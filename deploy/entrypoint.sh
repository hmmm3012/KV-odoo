#!/bin/bash
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${ODOO_ADMIN_PASSWD:?ODOO_ADMIN_PASSWD is required}"

CONF_DIR="/etc/odoo"
CONF_FILE="${CONF_DIR}/odoo.conf"
TEMPLATE="/opt/odoo/deploy/odoo.conf.template"

# Defaults for dev (single-process); production overrides via docker-compose.prod.yml / .env
export ODOO_WORKERS="${ODOO_WORKERS:-0}"
export ODOO_MAX_CRON_THREADS="${ODOO_MAX_CRON_THREADS:-1}"
export ODOO_PROXY_MODE="${ODOO_PROXY_MODE:-True}"
export ODOO_GEVENT_PORT="${ODOO_GEVENT_PORT:-8072}"
export ODOO_LIMIT_MEMORY_SOFT="${ODOO_LIMIT_MEMORY_SOFT:-2147483648}"
export ODOO_LIMIT_MEMORY_HARD="${ODOO_LIMIT_MEMORY_HARD:-2684354560}"
export ODOO_LIMIT_MEMORY_SOFT_GEVENT="${ODOO_LIMIT_MEMORY_SOFT_GEVENT:-1048576000}"
export ODOO_LIMIT_MEMORY_HARD_GEVENT="${ODOO_LIMIT_MEMORY_HARD_GEVENT:-1153433600}"
export ODOO_LIMIT_TIME_REAL="${ODOO_LIMIT_TIME_REAL:-120}"
export ODOO_LIMIT_TIME_CPU="${ODOO_LIMIT_TIME_CPU:-60}"
export ODOO_LIMIT_REQUEST="${ODOO_LIMIT_REQUEST:-8192}"

mkdir -p "${CONF_DIR}" /var/lib/odoo
chown -R odoo:odoo /var/lib/odoo 2>/dev/null || true

export POSTGRES_USER POSTGRES_PASSWORD ODOO_ADMIN_PASSWD
envsubst '${POSTGRES_USER} ${POSTGRES_PASSWORD} ${ODOO_ADMIN_PASSWD} ${ODOO_WORKERS} ${ODOO_MAX_CRON_THREADS} ${ODOO_PROXY_MODE} ${ODOO_GEVENT_PORT} ${ODOO_LIMIT_MEMORY_SOFT} ${ODOO_LIMIT_MEMORY_HARD} ${ODOO_LIMIT_MEMORY_SOFT_GEVENT} ${ODOO_LIMIT_MEMORY_HARD_GEVENT} ${ODOO_LIMIT_TIME_REAL} ${ODOO_LIMIT_TIME_CPU} ${ODOO_LIMIT_REQUEST}' < "${TEMPLATE}" > "${CONF_FILE}"
chmod 640 "${CONF_FILE}"
chown odoo:odoo "${CONF_FILE}" 2>/dev/null || true

CMD=(python3 /opt/odoo/odoo-bin -c "${CONF_FILE}")

if [[ -n "${ODOO_INIT_MODULES:-}" ]]; then
  CMD+=(-i "${ODOO_INIT_MODULES}")
fi

if [[ -n "${ODOO_UPDATE_MODULES:-}" ]]; then
  CMD+=(-u "${ODOO_UPDATE_MODULES}")
fi

if [[ $# -gt 0 ]]; then
  exec gosu odoo "$@"
else
  exec gosu odoo "${CMD[@]}"
fi
