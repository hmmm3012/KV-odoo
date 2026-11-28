#!/usr/bin/env bash
# Definition of done for one custom module (or --all).
# Runs static gates then upgrades + unit tests on a disposable DB.
# Never writes to odoo_19_test, production, or Odoo 18 staging.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
UPGRADE_DIR="${KV_ODOO19_UPGRADE_DIR:-/home/debian1/kv-odoo-19-upgrade}"
COMPOSE_PROJECT="kv-odoo-19-test"
export PATH="$HOME/.local/bin:$PATH"

RED=$'\033[31m'
GRN=$'\033[32m'
YLW=$'\033[33m'
BLD=$'\033[1m'
RST=$'\033[0m'

MODULE=""
ALL=0
KEEP_DB=0
SKIP_RUNTIME=0
declare -a GATE_NAMES=()
declare -a GATE_RESULTS=()
TMPDB=""
FILESTORE=""
LOG=""

usage() {
  cat <<'EOF'
Usage: scripts/agent-verify.sh <module> | --all
  --skip-runtime   only static gates (ruff, compile, XML, xpath, invariants)
  --keep-db        do not drop the temp database after a failed or successful run
EOF
}

ok()  { printf '%sPASS%s  %s\n' "$GRN" "$RST" "$*"; }
bad() { printf '%sFAIL%s  %s\n' "$RED" "$RST" "$*"; }
hdr() { printf '\n%s==> %s%s\n' "$BLD" "$*" "$RST"; }

record() {
  GATE_NAMES+=("$1")
  GATE_RESULTS+=("$2")
}

cleanup() {
  local rc=$?
  if [[ -n "$TMPDB" && "$KEEP_DB" -eq 0 ]]; then
    "$REPO/scripts/agent-reset-testdb.sh" --drop "$TMPDB" >/dev/null 2>&1 || true
  fi
  if [[ -n "$FILESTORE" && -d "$FILESTORE" ]]; then
    rm -rf "$FILESTORE"
  fi
  exit "$rc"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) ALL=1; shift ;;
    --skip-runtime) SKIP_RUNTIME=1; shift ;;
    --keep-db) KEEP_DB=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [[ -z "$MODULE" && "$1" != --* ]]; then
        MODULE="$1"; shift
      else
        echo "unknown argument: $1" >&2; usage; exit 2
      fi
      ;;
  esac
done

exec </dev/null

if [[ "$ALL" -eq 1 ]]; then
  rc=0
  for m in hr_attendance_portal hr_employee_kv hr_department_access kv_hr_contract; do
    echo "========== $m =========="
    if ! "$0" "$m" ${SKIP_RUNTIME:+--skip-runtime} ${KEEP_DB:+--keep-db}; then
      rc=1
    fi
  done
  exit "$rc"
fi

if [[ -z "$MODULE" ]]; then
  usage; exit 2
fi
if [[ ! -d "$REPO/custom/$MODULE" ]]; then
  echo "Unknown custom module: $MODULE (expected $REPO/custom/$MODULE)" >&2
  exit 2
fi

run_gate() {
  local name="$1"; shift
  hdr "$name"
  if "$@"; then
    ok "$name"
    record "$name" "PASS"
    return 0
  else
    bad "$name"
    record "$name" "FAIL"
    return 1
  fi
}

STATIC_FAIL=0

# --- ruff ---
if command -v ruff >/dev/null 2>&1; then
  if [[ -f "$REPO/pyproject.toml" ]]; then
    run_gate "ruff check custom/$MODULE" ruff check "custom/$MODULE" || STATIC_FAIL=1
  else
    run_gate "ruff check custom/$MODULE" ruff check "custom/$MODULE" || STATIC_FAIL=1
  fi
else
  printf '%sSKIP%s  ruff not on PATH (install standalone binary to ~/.local/bin)\n' "$YLW" "$RST"
  record "ruff check" "SKIP"
fi

# --- compile ---
run_gate "py_compile custom/$MODULE" python3 -m compileall -q "custom/$MODULE" || STATIC_FAIL=1

# --- XML well-formed ---
xml_parse() {
  python3 - "$MODULE" <<'PY'
import sys, pathlib, xml.etree.ElementTree as ET
mod = sys.argv[1]
root = pathlib.Path("custom") / mod
errors = 0
files = list(root.rglob("*.xml"))
for p in files:
    try:
        ET.parse(p)
    except Exception as exc:
        print(f"{p}: {exc}")
        errors += 1
print(f"parsed {len(files)} XML files, {errors} error(s)")
sys.exit(1 if errors else 0)
PY
}
run_gate "XML parse custom/$MODULE" xml_parse || STATIC_FAIL=1

# --- invariants ---
run_gate "Odoo 19 invariants" python3 "$REPO/scripts/check-odoo19-invariants.py" --repo "$REPO" || STATIC_FAIL=1

# --- xpath (lxml on host, else inside the already-running test container, read-only) ---
xpath_check() {
  local args=(--all-custom)
  # Limit to this module's views when possible: still need combined stack, but only report this module?
  # Check all custom views: a change in one module can break another inherit. Fast enough.
  if python3 -c 'from lxml import etree' >/dev/null 2>&1; then
    python3 "$REPO/scripts/xpath_check.py" --all-custom
    return
  fi
  if ! docker ps --format '{{.Names}}' | grep -qx 'kv-odoo-19-test-odoo-1'; then
    echo "lxml is not on the host and kv-odoo-19-test-odoo-1 is not running; cannot run xpath_check." >&2
    return 1
  fi
  # Copy script+module list into a temp path in the container without restarting it,
  # then run read-only (no database flag).
  docker exec kv-odoo-19-test-odoo-1 mkdir -p /tmp/kv-harness-scripts
  docker cp "$REPO/scripts/xpath_check.py" kv-odoo-19-test-odoo-1:/tmp/kv-harness-scripts/xpath_check.py
  docker cp "$REPO/scripts/installed-modules-19.txt" kv-odoo-19-test-odoo-1:/tmp/kv-harness-scripts/installed-modules-19.txt
  docker exec kv-odoo-19-test-odoo-1 python3 /tmp/kv-harness-scripts/xpath_check.py \
    --addons-root /opt/odoo --custom-root /opt/odoo-custom --all-custom
}
run_gate "xpath_check (73-module stack)" xpath_check || STATIC_FAIL=1

if [[ "$SKIP_RUNTIME" -eq 1 ]]; then
  echo
  echo "Skipped runtime gates (--skip-runtime)."
else
  if [[ "$STATIC_FAIL" -ne 0 ]]; then
    echo "Static gates failed; skipping runtime to avoid starting a temp DB."
  else
    trap cleanup EXIT
    hdr "Temp DB from template (not odoo_19_test)"
    TMPDB="$("$REPO/scripts/agent-reset-testdb.sh" --create)"
    echo "    temp DB: $TMPDB"
    if [[ "$TMPDB" != odoo_19_agent_* ]]; then
      echo "REFUSE: unexpected temp DB name $TMPDB" >&2
      exit 2
    fi
    FILESTORE="$(mktemp -d /tmp/kv-odoo-agent-fs-XXXX)"
    LOG="$(mktemp /tmp/kv-odoo-agent-log-XXXX)"
    hdr "odoo-bin -u $MODULE --test-enable on $TMPDB"
    set +e
    docker compose --project-directory "$UPGRADE_DIR" -p "$COMPOSE_PROJECT" \
      run --rm --no-deps --no-TTY --name "kv-odoo-19-agent-$$" \
      -v "$FILESTORE:/var/lib/odoo" \
      -e ODOO_MAX_CRON_THREADS=0 \
      odoo python3 /opt/odoo/odoo-bin -c /etc/odoo/odoo.conf \
        -d "$TMPDB" --db-filter="^${TMPDB}$" \
        --http-interface=127.0.0.1 --http-port=8069 \
        --max-cron-threads=0 --workers=0 \
        --limit-time-real=0 --limit-time-cpu=0 \
        --stop-after-init \
        -u "$MODULE" --test-enable --test-tags="/$MODULE" \
        --log-level=test 2>&1 | tee "$LOG"
    rc=${PIPESTATUS[0]}
    set -e

    # Observability signals
    echo
    echo "--- signals ---"
    tb=$(grep -c 'Traceback (most recent call last)' "$LOG" || true)
    err=$(grep -cE '^[0-9-].* ERROR ' "$LOG" || true)
    echo "    odoo exit: $rc"
    echo "    Traceback count: $tb"
    echo "    ERROR lines: $err"
    if grep -E 'odoo_19_test[^-_a-zA-Z0-9]|db_name = odoo_19_test' "$LOG" | grep -vq "$TMPDB"; then
      echo "    warning: log mentions odoo_19_test; confirm the run used $TMPDB"
    fi
    echo "    target DB (expected $TMPDB):"
    grep -E "database.*$TMPDB|'$TMPDB'|db:$TMPDB" "$LOG" | head -5 | sed 's/^/      /' || true

    tests_ok=1
    if [[ "$rc" -ne 0 ]]; then
      tests_ok=0
    fi
    # Odoo prints "FAIL" on assertion failures even if we also check exit code
    if grep -qE '^[0-9].* ERROR .*(test|FAIL)' "$LOG"; then
      tests_ok=0
    fi
    if [[ "$tests_ok" -eq 1 ]]; then
      ok "upgrade + unit tests $MODULE on $TMPDB"
      record "upgrade+tests $MODULE" "PASS"
    else
      bad "upgrade + unit tests $MODULE on $TMPDB (see log $LOG)"
      record "upgrade+tests $MODULE" "FAIL"
    fi
  fi
fi

echo
printf '%s==> Summary%s\n' "$BLD" "$RST"
fail=0
for i in "${!GATE_NAMES[@]}"; do
  r="${GATE_RESULTS[$i]}"
  if [[ "$r" == "PASS" ]]; then
    printf '  %sPASS%s  %s\n' "$GRN" "$RST" "${GATE_NAMES[$i]}"
  elif [[ "$r" == "SKIP" ]]; then
    printf '  %sSKIP%s  %s\n' "$YLW" "$RST" "${GATE_NAMES[$i]}"
  else
    printf '  %sFAIL%s  %s\n' "$RED" "$RST" "${GATE_NAMES[$i]}"
    fail=1
  fi
done
if [[ "$STATIC_FAIL" -ne 0 ]]; then
  fail=1
fi
if [[ "$fail" -ne 0 ]]; then
  echo "agent-verify: FAIL"
  exit 1
fi
echo "agent-verify: PASS"
exit 0
