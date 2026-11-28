#!/usr/bin/env bash
# Idempotent cleanup of harness/temp artifacts. Never touches production data,
# odoo_19_test, or the template DB.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "cleanup.sh in $REPO"
# Temp filestore/logs from agent-verify
rm -rf /tmp/kv-odoo-agent-fs-* /tmp/kv-odoo-agent-log-* /tmp/e2e-body /tmp/init-*.txt /tmp/verify-*.out /tmp/reset-trace.txt 2>/dev/null || true

# Leftover one-off test DBs (name-gated inside the script)
if [[ -x "$REPO/scripts/agent-reset-testdb.sh" ]] && command -v docker >/dev/null; then
  if docker ps --format "{{.Names}}" </dev/null | grep -qx "kv-odoo-19-test-db-1"; then
    names=$(docker compose --project-directory /home/debian1/kv-odoo-19-upgrade -p kv-odoo-19-test \
      exec -T db bash -c 'psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT datname FROM pg_database WHERE datname LIKE '"'odoo_19_agent_%'"'"' </dev/null || true)
    for name in $names; do
      name=$(echo "$name" | tr -d "[:space:]")
      [[ -z "$name" ]] && continue
      echo "dropping leftover $name"
      "$REPO/scripts/agent-reset-testdb.sh" --drop "$name" || true
    done
  fi
fi

# Bytecode under custom/ (gitignored) — optional, harmless
find "$REPO/custom" "$REPO/scripts" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

echo "cleanup.sh: done"
