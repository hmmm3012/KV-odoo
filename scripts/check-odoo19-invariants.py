#!/usr/bin/env python3
"""Enforce Odoo 19 / safety invariants for the Kiến Việt custom tree.

Scans custom/ and scripts/ (plus git status for core edits). Exit 1 on violations.
Each finding includes a hint on how to fix it.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

GENDER_ALLOW = {
    "id_card_qr.py",
    "id_card_ocr.py",
    "intro_letter_pdf.py",
    "intro_letter_odt.py",
    "intro_letter_docx.py",
    "intro_letter_wizard.py",
    "test_id_card_qr.py",
    "test_id_card_ocr.py",
    "test_intro_letter_templates.py",
}

HR_CONTRACT_CODE = re.compile(
    r"""(?x)
    env\[\s*['"]hr\.contract(?:\.[^'"]+)?['"]\s*\]
    | _inherit\s*=\s*['"]hr\.contract(?:\.[^'"]+)?['"]
    | _name\s*=\s*['"]hr\.contract(?:\.[^'"]+)?['"]
    | request\.env\[\s*['"]hr\.contract
    """
)
SQL_CONSTRAINTS = re.compile(r"\b_sql_constraints\b")
TYPE_JSON = re.compile(r"""type\s*=\s*['"]json['"]""")
GENDER_FIELD = re.compile(
    r"""(?x)
    gender\s*=\s*fields\.
    | \.gender\s*=
    | write\(\s*\{[^}]*['"]gender['"]
    | create\(\s*\{[^}]*['"]gender['"]
    """
)
PROD_HOST = re.compile(
    r"hrmkienviet\.ddns\.net|/home/debian1/KV-odoo(?:-staging)?(?:/|$)"
)
# Mentions that are clearly prohibitions are allowed.
PROD_ALLOW_LINE = re.compile(
    r"(CẤM|cấm|do not|Don't|khong dung|không đụng|MUST not|must not|REFUSE|production or Odoo 18)",
    re.I,
)

findings: list[str] = []


def add(path: Path, lineno: int, msg: str, hint: str):
    rel = path
    try:
        rel = path.relative_to(REPO)
    except ValueError:
        pass
    findings.append(f"{rel}:{lineno}: {msg}\n    hint: {hint}")


def iter_files(roots: list[Path], suffixes: tuple[str, ...]):
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            if root.suffix in suffixes or root.name in {"Makefile", "init.sh"}:
                yield root
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in {".git", "__pycache__", ".venv", "node_modules"} for part in p.parts):
                continue
            if p.suffix in suffixes or p.name in {"Makefile", "init.sh"}:
                yield p


def scan_python(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    allowed_gender = path.name in GENDER_ALLOW
    for i, line in enumerate(lines, 1):
        stripped = line.split("#", 1)[0]
        if HR_CONTRACT_CODE.search(stripped):
            add(
                path,
                i,
                "uses hr.contract",
                "Odoo 19 merged hr.contract into hr.version; inherit or search hr.version instead.",
            )
        if SQL_CONSTRAINTS.search(stripped):
            add(
                path,
                i,
                "uses _sql_constraints",
                "Declare models.Constraint on the model instead of _sql_constraints.",
            )
        if TYPE_JSON.search(stripped):
            add(
                path,
                i,
                'HTTP route type="json"',
                'Use type="jsonrpc" (type="json" was removed).',
            )
        if not allowed_gender and GENDER_FIELD.search(stripped):
            add(
                path,
                i,
                "writes or declares employee field gender",
                'Odoo 19 renamed hr.employee.gender to sex. Parsers may keep an internal dict key "gender" and map it in _id_card_fields().',
            )


def scan_scripts(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(text.splitlines(), 1):
        if not PROD_HOST.search(line):
            continue
        if PROD_ALLOW_LINE.search(line):
            continue
        # comments that only document the forbidden target in a refuse/case path
        if "KV-odoo" in line and any(k in line for k in ("case ", "REFUSE", "CẤM", "cấm", "compose `kv-odoo`", "project `kv-odoo`")):
            continue
        add(
            path,
            i,
            "script mentions production or Odoo 18 staging path/hostname",
            "Keep production hostnames out of executable scripts except in explicit refuse/guard clauses. Do not call compose project kv-odoo or kv-odoo-staging.",
        )


def scan_git():
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain", "-uall", "--", "odoo", "addons"],
            cwd=REPO,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for line in out.splitlines():
        if not line.strip():
            continue
        findings.append(
            f"git: {line}\n    hint: Do not modify core odoo/ or addons/. Keep changes in custom/ and scripts/."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None)
    args = parser.parse_args()
    repo = (args.repo or Path(__file__).resolve().parent.parent).resolve()
    # Bind for helpers that read the module-level REPO
    globals()["REPO"] = repo

    # Language/API invariants apply to product code in custom/.
    # The linter itself mentions forbidden tokens in regexes and must not self-flag.
    py_roots = [REPO / "custom"]
    for p in iter_files(py_roots, (".py",)):
        scan_python(p)
    script_roots = [REPO / "scripts", REPO / "init.sh", REPO / "Makefile"]
    for p in iter_files(script_roots, (".sh", ".py", ".mjs", ".sql", ".yml")):
        scan_scripts(p)
    scan_git()

    if findings:
        print(f"check-odoo19-invariants: {len(findings)} violation(s)")
        print("\n".join(findings))
        sys.exit(1)
    print("check-odoo19-invariants: OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
