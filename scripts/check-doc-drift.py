#!/usr/bin/env python3
"""Fail if AGENTS.md / docs / Cursor rules point at missing repo paths."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKTICK = re.compile(r"`([^`]+)`")

SOURCES = [
    REPO / "AGENTS.md",
    *(REPO / ".cursor/rules").glob("*.mdc"),
    *(REPO / "docs").glob("*.md"),
]

# Paths that are allowed to be mentioned as future or external.
SKIP_EXACT = {
    "pyproject.toml",  # actually exists after phase 2
}


def looks_like_repo_path(s: str) -> bool:
    if s.startswith(("docs/", ".cursor/", "custom/", "scripts/", "init.sh", "feature_list.json", "PROGRESS.md", "AGENTS.md", "session-handoff.md", "Makefile", "pyproject.toml", ".github/")):
        return True
    if s.endswith((".md", ".mdc", ".json", ".sh", ".py", ".xml", ".js", ".po", ".toml", ".yml", ".mjs")) and "/" in s:
        return True
    return False


def main():
    missing = []
    checked = 0
    for src in SOURCES:
        if not src.is_file():
            continue
        for raw in BACKTICK.findall(src.read_text(encoding="utf-8")):
            s = raw.strip()
            if s.startswith("custom/<module>"):
                for mod in ("hr_attendance_portal", "hr_employee_kv", "hr_department_access", "kv_hr_contract"):
                    p = REPO / s.replace("custom/<module>", f"custom/{mod}")
                    checked += 1
                    if not p.exists():
                        missing.append(f"{src.relative_to(REPO)}: {p.relative_to(REPO)}")
                continue
            if not looks_like_repo_path(s):
                continue
            checked += 1
            if not (REPO / s).exists():
                missing.append(f"{src.relative_to(REPO)}: {s}")
    print(f"check-doc-drift: checked {checked} paths")
    if missing:
        print("MISSING:")
        for item in missing:
            print(" -", item)
        sys.exit(1)
    print("check-doc-drift: OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
