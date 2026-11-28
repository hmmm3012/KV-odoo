#!/usr/bin/env bash
# End-to-end smoke for the Odoo 19 test stack.
# Playwright / Chromium are NOT used: they are not in image kv-odoo:19, and
# this script will not install a browser on the company server.
# Instead we check HTTP surfaces and (via unit tests) get_views / menus by role.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

BASE="${E2E_BASE_URL:-http://127.0.0.1:8269}"
fail=0

check() {
  local url="$1" expect="${2:-200}"
  local code
  code=$(curl -sS -o /tmp/e2e-body -w "%{http_code}" --max-time 8 "$url" || echo "000")
  if [[ "$code" == "$expect" ]]; then
    echo "PASS  $url -> $code"
  else
    echo "FAIL  $url -> $code (expected $expect)"
    fail=1
  fi
}

echo "e2e-smoke (HTTP alternative; not Playwright) against $BASE"
check "$BASE/web/login" 200
check "$BASE/attendance" 200

if grep -q -i "odoo\|login\|chấm công\|attendance" /tmp/e2e-body; then
  echo "PASS  /attendance body looks like the portal"
else
  echo "FAIL  /attendance body did not contain an expected marker"
  fail=1
fi

# JS widget source is in the repo (bundled into web.assets_backend at runtime).
repo="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$repo/custom/hr_employee_kv/static/src/id_card_autofill.js" ]]; then
  echo "PASS  id_card_autofill.js present in the repo"
else
  echo "FAIL  missing id_card_autofill.js"
  fail=1
fi

echo
echo "Role/menu/get_views checks live in unit tests:"
echo "  ./scripts/agent-verify.sh hr_employee_kv   # test_menus_and_i18n.py"
echo "  ./scripts/agent-verify.sh kv_hr_contract   # PDF /contracts/pdf/<id>"
echo "This script does not log in as a real user and does not write to odoo_19_test."

if [[ "$fail" -ne 0 ]]; then
  echo "e2e-smoke: FAIL"
  exit 1
fi
echo "e2e-smoke: PASS"
exit 0
