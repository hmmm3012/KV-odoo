#!/usr/bin/env bash
# Create or drop a one-off Odoo 19 test database cloned from odoo_19_test_tpl.
# Never touches odoo_19_test (the hand-test DB), production, or Odoo 18 staging.
set -euo pipefail

UPGRADE_DIR="${KV_ODOO19_UPGRADE_DIR:-/home/debian1/kv-odoo-19-upgrade}"
COMPOSE_PROJECT="kv-odoo-19-test"
TEMPLATE_DB="odoo_19_test_tpl"
SOURCE_DB="odoo_19_test"
SANITIZE_SQL="$UPGRADE_DIR/scripts/rehearsal-resanitize.sql"

usage() {
  cat <<'EOF'
Usage:
  scripts/agent-reset-testdb.sh --ensure-template
  scripts/agent-reset-testdb.sh --create [name]
  scripts/agent-reset-testdb.sh --drop <name>
  scripts/agent-reset-testdb.sh --print-status

Creates a disposable DB from template odoo_19_test_tpl (itself a pg_dump of
odoo_19_test). Does not terminate connections to odoo_19_test, does not
restart containers, and refuses to drop odoo_19_test / production DBs.
EOF
}

refuse_forbidden_db() {
  local name="${1:-}"
  case "$name" in
    odoo_19_test|odoo|postgres|template0|template1|"")
      echo "REFUSE: will not create/drop protected database '$name'" >&2
      exit 2
      ;;
  esac
  if [[ "$name" == *".."* ]]; then
    echo "REFUSE: invalid database name '$name'" >&2
    exit 2
  fi
}

psql_postgres() {
  docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
    exec -T db bash -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -P pager=off'
}

psql_db() {
  local db="$1"
  docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
    exec -T db bash -c "psql -U \"\$POSTGRES_USER\" -d $(printf '%q' "$db") -v ON_ERROR_STOP=1 -P pager=off"
}

db_exists() {
  local name="$1"
  docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
    exec -T db bash -c 'psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '\'''"$name"''\''"' \
    | tr -d '[:space:]'
}

wait_for_template_restore() {
  # If a previous dump/restore is still running, wait rather than starting a second one.
  local tries=0
  while docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
      exec -T db bash -c 'ps -eo args | grep -E "[p]g_dump.*odoo_19_test|[p]sql.*odoo_19_test_tpl"' >/dev/null 2>&1; do
    tries=$((tries + 1))
    if (( tries > 180 )); then
      echo "Timeout waiting for in-flight odoo_19_test_tpl restore" >&2
      exit 1
    fi
    sleep 2
  done
}

ensure_template() {
  wait_for_template_restore
  if [[ "$(db_exists "$TEMPLATE_DB")" == "1" ]]; then
    local size
    size=$(docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
      exec -T db bash -c 'psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT pg_database_size('\''odoo_19_test_tpl'\'')"')
    # A finished clone of the 342MB source is well above 100MB; 16MB means a partial create.
    if [[ -n "$size" && "$size" -gt 100000000 ]]; then
      echo "template $TEMPLATE_DB already present"
      return 0
    fi
    echo "template $TEMPLATE_DB looks incomplete (size=$size); rebuilding"
    psql_postgres <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TEMPLATE_DB' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS $TEMPLATE_DB;
SQL
  fi

  echo "Creating $TEMPLATE_DB from template1, then restoring a dump of $SOURCE_DB (odoo_19_test stays up)"
  psql_postgres <<SQL
CREATE DATABASE $TEMPLATE_DB OWNER odoo19 TEMPLATE template1;
SQL
  docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
    exec -T db bash -c 'pg_dump -U "$POSTGRES_USER" --no-owner --no-acl odoo_19_test | psql -U "$POSTGRES_USER" -d odoo_19_test_tpl -v ON_ERROR_STOP=1 --quiet'
  if [[ -f "$SANITIZE_SQL" ]]; then
    echo "Sanitizing $TEMPLATE_DB (cron/mail/fetchmail off)"
    psql_db "$TEMPLATE_DB" < "$SANITIZE_SQL"
  fi
  psql_postgres <<SQL
ALTER DATABASE $TEMPLATE_DB IS_TEMPLATE true;
SQL
  echo "template $TEMPLATE_DB ready"
}

create_db() {
  ensure_template >&2
  local name="${1:-}"
  if [[ -z "$name" ]]; then
    name="odoo_19_agent_$(date +%Y%m%d_%H%M%S)_$$"
  fi
  refuse_forbidden_db "$name"
  if [[ ! "$name" =~ ^odoo_19_agent_[A-Za-z0-9_]+$ ]]; then
    echo "REFUSE: temp DB name must match odoo_19_agent_*  (got $name)" >&2
    exit 2
  fi
  # Cloning a template requires no other connections to the template.
  psql_postgres <<SQL >&2
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TEMPLATE_DB' AND pid <> pg_backend_pid();
CREATE DATABASE $name OWNER odoo19 TEMPLATE $TEMPLATE_DB;
SQL
  # stdout is the name only, so callers can capture it safely.
  printf '%s\n' "$name"
}

drop_db() {
  local name="${1:-}"
  refuse_forbidden_db "$name"
  if [[ ! "$name" =~ ^odoo_19_agent_[A-Za-z0-9_]+$ ]]; then
    echo "REFUSE: will only drop odoo_19_agent_* databases (got $name)" >&2
    exit 2
  fi
  psql_postgres <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$name' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS $name;
SQL
  echo "dropped $name"
}

print_status() {
  docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
    exec -T db bash -c 'psql -U "$POSTGRES_USER" -d postgres -P pager=off -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size, datistemplate FROM pg_database WHERE datname LIKE '\''odoo%'\'' ORDER BY 1;"'
}

# Detach from caller stdin so `ssh bash -s` / CI heredocs are not consumed by
# `docker compose exec -T`. Command-specific heredocs still work.
exec </dev/null

cmd="${1:-}"
case "$cmd" in
  --ensure-template) ensure_template ;;
  --create) create_db "${2:-}" ;;
  --drop) drop_db "${2:-}" ;;
  --print-status|--print-only) print_status ;;
  -h|--help|"") usage ;;
  *) echo "unknown argument: $cmd" >&2; usage; exit 2 ;;
esac
