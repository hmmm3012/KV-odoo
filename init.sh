#!/usr/bin/env bash
# init.sh — chuẩn khởi động phiên (kiểm tra nền, không nâng cấp module, không đụng production)
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

RED=$'\033[31m'
GRN=$'\033[32m'
YLW=$'\033[33m'
BLD=$'\033[1m'
RST=$'\033[0m'
fail=0
warn=0

ok()  { printf '%sOK%s    %s\n' "$GRN" "$RST" "$*"; }
bad() { printf '%sFAIL%s  %s\n' "$RED" "$RST" "$*"; fail=1; }
note(){ printf '%sWARN%s  %s\n' "$YLW" "$RST" "$*"; warn=1; }
hdr() { printf '\n%s==> %s%s\n' "$BLD" "$*" "$RST"; }

# Refuse to run if this script was copied into a production/staging-18 tree.
case "$PWD" in
  /home/debian1/KV-odoo|/*/KV-odoo|/home/debian1/KV-odoo-staging|/*/KV-odoo-staging)
    echo "REFUSE: init.sh must not run from production or Odoo 18 staging." >&2
    exit 2
    ;;
esac

hdr "Working directory"
echo "    $PWD"

hdr "Git"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  branch=$(git rev-parse --abbrev-ref HEAD)
  commit=$(git log -1 --format='%h %s' 2>/dev/null || echo "(no commits)")
  echo "    branch: $branch"
  echo "    head:   $commit"
  git status -sb | sed 's/^/    /'
  if [[ "$branch" == "19.0-upgrade" ]]; then
    ok "đúng nhánh 19.0-upgrade"
  else
    note "đang ở nhánh $branch (kỳ vọng 19.0-upgrade)"
  fi
else
  bad "không phải git repo"
fi

hdr "Kiểm tra nền tĩnh (custom/)"
if python3 -m compileall -q custom/; then
  ok "python3 -m compileall custom/"
else
  bad "compileall custom/ thất bại"
fi

if command -v ruff >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
  if ruff check custom/; then
    ok "ruff check custom/"
  else
    bad "ruff check custom/ thất bại"
  fi
else
  echo "    (bỏ qua ruff: chưa có trên PATH hoặc chưa có pyproject.toml — Giai đoạn 2)"
fi

if [[ -f scripts/xpath_check.py ]]; then
  xpath_ok=0
  if python3 -c "from lxml import etree" >/dev/null 2>&1; then
    python3 scripts/xpath_check.py --all-custom && xpath_ok=1
  elif docker ps --format "{{.Names}}" </dev/null | grep -qx "kv-odoo-19-test-odoo-1"; then
    docker exec kv-odoo-19-test-odoo-1 mkdir -p /tmp/kv-harness-scripts </dev/null
    docker cp scripts/xpath_check.py kv-odoo-19-test-odoo-1:/tmp/kv-harness-scripts/xpath_check.py
    docker cp scripts/installed-modules-19.txt kv-odoo-19-test-odoo-1:/tmp/kv-harness-scripts/installed-modules-19.txt
    docker exec kv-odoo-19-test-odoo-1 python3 /tmp/kv-harness-scripts/xpath_check.py --addons-root /opt/odoo --custom-root /opt/odoo-custom --all-custom </dev/null && xpath_ok=1
  else
    echo "    (không có lxml trên host và container test không chạy)"
  fi
  if [[ "$xpath_ok" -eq 1 ]]; then
    ok "scripts/xpath_check.py --all-custom"
  else
    bad "xpath_check.py thất bại"
  fi
else
  echo "    (bỏ qua xpath_check.py: chưa có trong repo)"
fi

if [[ -f scripts/check-odoo19-invariants.py ]]; then
  if python3 scripts/check-odoo19-invariants.py; then
    ok "scripts/check-odoo19-invariants.py"
  else
    bad "check-odoo19-invariants.py thất bại"
  fi
fi

hdr "feature_list.json và PROGRESS.md"
if [[ -f feature_list.json ]]; then
  if python3 -m json.tool feature_list.json >/dev/null; then
    ok "feature_list.json là JSON hợp lệ"
    python3 -c '
import json
from pathlib import Path
data = json.loads(Path("feature_list.json").read_text(encoding="utf-8"))
feats = data.get("features") or []
print("    project: %s  last_updated: %s" % (data.get("project"), data.get("last_updated")))
print("    rules: %s" % (data.get("rules"),))
active = [f for f in feats if f.get("status") == "in_progress"]
if len(active) > 1:
    print("    WARNING: WIP>1, đang in_progress: %s" % [f.get("id") for f in active])
elif len(active) == 1:
    print("    in_progress (WIP=1): %s — %s" % (active[0].get("id"), active[0].get("title")))
else:
    print("    in_progress: (không có)")
for f in feats:
    flag = "PASS" if f.get("passes") else "...."
    ev = len(f.get("evidence") or [])
    print("    [%s] %s  %s: %s  (evidence=%d)" % (flag, str(f.get("status","?")).ljust(12), f.get("id"), f.get("title"), ev))
'
  else
    bad "feature_list.json không phải JSON hợp lệ"
  fi
else
  bad "thiếu feature_list.json"
fi

if [[ -f PROGRESS.md ]]; then
  ok "có PROGRESS.md"
  echo "    --- 12 dòng cuối PROGRESS.md ---"
  tail -n 12 PROGRESS.md | sed "s/^/    /"
else
  bad "thiếu PROGRESS.md"
fi

hdr "Môi trường Docker kv-odoo-19-test (không đụng production)"
if [[ "${INIT_SKIP_DOCKER:-}" == "1" ]]; then
  note "INIT_SKIP_DOCKER=1 — bỏ qua kiểm tra container và HTTP"
else
  if ! command -v docker >/dev/null 2>&1; then
    note "không có docker trên PATH — bỏ qua kiểm tra container/HTTP"
  else
    # Chỉ đọc trạng thái project test. Không restart, không compose lên kv-odoo / kv-odoo-staging.
    if docker ps --format "{{.Names}} {{.Status}}" | grep -q "^kv-odoo-19-test-db-1 "; then
      ok "container kv-odoo-19-test-db-1 đang chạy"
    else
      bad "container kv-odoo-19-test-db-1 không chạy"
    fi
    if docker ps --format "{{.Names}} {{.Status}}" | grep -q "^kv-odoo-19-test-odoo-1 "; then
      ok "container kv-odoo-19-test-odoo-1 đang chạy"
    else
      bad "container kv-odoo-19-test-odoo-1 không chạy"
    fi

    login_code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8269/web/login || echo "000")
    att_code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8269/attendance || echo "000")
    if [[ "$login_code" == "200" ]]; then
      ok "HTTP http://127.0.0.1:8269/web/login -> 200"
    else
      bad "HTTP /web/login -> $login_code (kỳ vọng 200)"
    fi
    if [[ "$att_code" == "200" ]]; then
      ok "HTTP http://127.0.0.1:8269/attendance -> 200"
    else
      bad "HTTP /attendance -> $att_code (kỳ vọng 200)"
    fi
  fi
fi

hdr "Lệnh kiểm chứng đầy đủ (chạy sau khi sửa, trên DB tạm — không phải bước của init.sh)"
if [[ -x scripts/agent-verify.sh ]]; then
  echo "    ./scripts/agent-verify.sh <ten_module>"
else
  echo "    ./scripts/agent-verify.sh <ten_module>  (sẽ có từ Giai đoạn 2)"
fi
echo "    Môi trường test: docker compose -p kv-odoo-19-test (thư mục /home/debian1/kv-odoo-19-upgrade)"
echo "    CẤM: docker compose / restart trên kv-odoo (production) hoặc kv-odoo-staging (Odoo 18)"

echo
if [[ "$fail" -ne 0 ]]; then
  printf "%sFAIL%s  Kiểm tra nền thất bại — sửa nền trước, chưa làm tính năng mới.\\n" "$RED" "$RST"
  exit 1
fi
if [[ "$warn" -ne 0 ]]; then
  printf "%sOK với cảnh báo%s  Nền đủ để làm việc, hãy đọc các WARN ở trên.\\n" "$YLW" "$RST"
  exit 0
fi
printf "%sOK%s  Kiểm tra nền đạt.\\n" "$GRN" "$RST"
exit 0
