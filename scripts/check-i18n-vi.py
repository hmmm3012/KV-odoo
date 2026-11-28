#!/usr/bin/env python3
"""Report obvious Vietnamese i18n gaps in custom modules. Exit 0 unless --strict."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MSGID = re.compile(r'^msgid "(.+)"\s*$', re.M)
EMPTY = re.compile(r'^msgid "(.+)"\s*\nmsgstr ""\s*$', re.M)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    issues = []
    for mod in ("hr_attendance_portal", "hr_employee_kv", "hr_department_access", "kv_hr_contract"):
        po = REPO / "custom" / mod / "i18n" / "vi.po"
        if not po.is_file():
            issues.append(f"{mod}: no i18n/vi.po")
            continue
        text = po.read_text(encoding="utf-8", errors="replace")
        empty = [m.group(1) for m in EMPTY.finditer(text) if m.group(1)]
        if empty:
            issues.append(f"{mod}: {len(empty)} empty msgstr in vi.po (first: {empty[0][:80]})")
    print("check-i18n-vi:")
    if not issues:
        print("  no gaps found")
    else:
        for i in issues:
            print("  -", i)
    if args.strict and issues:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
