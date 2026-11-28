#!/usr/bin/env python3
"""Check custom inherited views against the installed Odoo 19 HR-only stack.

Usage:
  python3 scripts/xpath_check.py --all-custom
  python3 scripts/xpath_check.py custom/hr_employee_kv/views/hr_employee_views.xml
  python3 scripts/xpath_check.py --addons-root /opt/odoo --custom-root /opt/odoo-custom --all-custom

Exit 0 if every xpath/field inherit target exists on the combined parent arch.
Prints a hint when a missing node looks like a removed Odoo 18 model (hr.contract, hr_timesheet, account, stock, project).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    sys.stderr.write(
        "xpath_check.py needs lxml. On the company server run it inside "
        "kv-odoo-19-test-odoo-1 (see scripts/agent-verify.sh), or install lxml.\n"
    )
    sys.exit(2)


def _hasclass(context, *klasses):
    """Odoo view inheritance helper: //div[hasclass('oe_title')]."""
    node = context.context_node
    current = set((node.get("class") or "").split())
    return current >= set(klasses)


def _register_odoo_xpath_functions():
    try:
        ns = etree.FunctionNamespace(None)
    except Exception:
        return
    ns["hasclass"] = _hasclass


_register_odoo_xpath_functions()

REMOVED_HINTS = {
    "hr_timesheet": "hr_timesheet is uninstalled on the 73-module HR stack; do not inherit its views or buttons.",
    "hr.contract": "hr.contract was merged into hr.version in Odoo 19; inherit hr.version instead.",
    "account": "account is uninstalled; do not inherit accounting views.",
    "stock": "stock is uninstalled; do not inherit inventory views.",
    "project": "project is uninstalled; do not inherit project views.",
}


def detect_roots() -> tuple[Path, Path, Path]:
    """Return (odoo_root, addons_dir, custom_dir)."""
    here = Path(__file__).resolve()
    repo = here.parent.parent
    candidates = [
        Path("/opt/odoo"),
        Path("/home/debian1/kv-odoo-19-upgrade/odoo-19.0"),
        repo.parent / "odoo-19.0",
        repo / "odoo",  # last-resort: tree vendored inside the git repo
    ]
    odoo_root = None
    for c in candidates:
        if (c / "addons").is_dir() and (c / "odoo").is_dir():
            odoo_root = c
            break
    if odoo_root is None:
        raise SystemExit("Cannot find Odoo 19 source (looked for addons/ + odoo/). Pass --addons-root.")
    custom_candidates = [
        Path("/opt/odoo-custom"),
        repo / "custom",
    ]
    custom = next((c for c in custom_candidates if c.is_dir()), repo / "custom")
    return odoo_root, odoo_root / "addons", custom


def load_module_list(script_dir: Path) -> list[str]:
    path = script_dir / "installed-modules-19.txt"
    if not path.is_file():
        return ["base", "web", "mail", "hr", "hr_attendance", "hr_holidays", "calendar", "resource", "hr_skills", "portal"]
    mods = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            mods.append(line)
    return mods


def iter_view_xml(module_dir: Path):
    for sub in ("views", "wizard", "data", "report", "static/src/xml"):
        d = module_dir / sub
        if d.is_dir():
            yield from d.rglob("*.xml")
        elif d.suffix == ".xml" and d.is_file():
            yield d


def parse_records(path: Path, default_mod: str):
    try:
        doc = etree.parse(str(path))
    except Exception as exc:
        print(f"WARN cannot parse {path}: {exc}")
        return
    for r in doc.iter("record"):
        if r.get("model") != "ir.ui.view":
            continue
        rid = r.get("id") or ""
        arch = r.find("field[@name='arch']")
        inh = r.find("field[@name='inherit_id']")
        xid = rid if "." in rid else f"{default_mod}.{rid}"
        parent = None
        if inh is not None:
            parent = inh.get("ref")
        yield xid, arch, parent, default_mod, path, r


def collect_core(odoo_root: Path, addons: Path, modules: list[str]):
    records = {}
    files = []
    base_views = odoo_root / "odoo" / "addons" / "base"
    if base_views.is_dir():
        files += [(base_views, "base")]
    for m in modules:
        d = addons / m
        if d.is_dir():
            files.append((d, m))
        else:
            d2 = odoo_root / "odoo" / "addons" / m
            if d2.is_dir():
                files.append((d2, m))
    for directory, mod in files:
        for xml in iter_view_xml(directory):
            for xid, arch, parent, mod, path, rec in parse_records(xml, mod):
                records[xid] = (arch, parent, mod, path)
    return records


def collect_custom(custom: Path, modules: list[str]):
    records = {}
    for m in modules:
        d = custom / m
        if not d.is_dir():
            continue
        for xml in iter_view_xml(d):
            for xid, arch, parent, mod, path, rec in parse_records(xml, m):
                records[xid] = (arch, parent, mod, path, rec)
    # also scan any other custom dirs
    for d in custom.iterdir() if custom.is_dir() else []:
        if not d.is_dir() or d.name.startswith(".") or d.name == "docs":
            continue
        if d.name in modules:
            continue
        for xml in iter_view_xml(d):
            for xid, arch, parent, mod, path, rec in parse_records(xml, d.name):
                records[xid] = (arch, parent, mod, path, rec)
    return records


def resolve_parent(ref: str, records: dict, current_mod: str):
    if ref in records:
        return ref
    if "." not in ref:
        cand = f"{current_mod}.{ref}"
        if cand in records:
            return cand
    return ref


def arch_root(arch_field):
    if arch_field is None or len(arch_field) == 0:
        return None
    return etree.fromstring(etree.tostring(arch_field[0]))


def apply(base, spec):
    missing = []
    if spec is None:
        return missing
    for node in spec:
        if not isinstance(node.tag, str):
            continue
        if node.tag == "xpath":
            expr = node.get("expr")
        elif node.tag == "field" and node.get("name") and node.get("position"):
            expr = f"//field[@name='{node.get('name')}']"
        else:
            continue
        try:
            found = base.xpath(expr)
        except Exception as exc:
            missing.append((expr, f"bad xpath: {exc}"))
            continue
        if not found:
            missing.append((expr, "missing"))
            continue
        tgt = found[0]
        pos = node.get("position", "inside")
        kids = [etree.fromstring(etree.tostring(k)) for k in node if isinstance(k.tag, str)]
        parent = tgt.getparent()
        if pos == "inside":
            tgt.extend(kids)
        elif pos == "after" and parent is not None:
            i = parent.index(tgt)
            for k in reversed(kids):
                parent.insert(i + 1, k)
        elif pos == "before" and parent is not None:
            i = parent.index(tgt)
            for k in kids:
                parent.insert(i, k)
                i += 1
        elif pos == "replace" and parent is not None:
            i = parent.index(tgt)
            parent.remove(tgt)
            for k in kids:
                parent.insert(i, k)
                i += 1
        elif pos == "attributes":
            continue
    return missing


def combined(xid: str, core: dict, custom: dict, skip_xid=None):
    if xid not in core and xid not in custom:
        return None
    src = core.get(xid) or custom.get(xid)
    arch = src[0]
    base = arch_root(arch)
    if base is None:
        return None
    # apply other inherits of this parent from core then custom (except the view under test)
    for store in (core, custom):
        for cx, val in store.items():
            if cx == skip_xid:
                continue
            parent = val[1]
            if not parent:
                continue
            pref = resolve_parent(parent, {**core, **{k: v[:3] + (v[3],) for k, v in custom.items()}}, val[2])
            if pref == xid or parent == xid:
                apply(base, val[0])
    return base


def hint_for(ref: str, expr: str) -> str:
    blob = f"{ref} {expr}"
    for key, msg in REMOVED_HINTS.items():
        if key in blob:
            return msg
    return "Check the parent view on the 73-module HR stack; the node may have been renamed or removed in Odoo 19."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*")
    parser.add_argument("--all-custom", action="store_true")
    parser.add_argument("--addons-root", type=Path)
    parser.add_argument("--custom-root", type=Path)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    odoo_root, addons, custom = detect_roots()
    if args.addons_root:
        odoo_root = args.addons_root
        addons = odoo_root / "addons"
    if args.custom_root:
        custom = args.custom_root
    modules = load_module_list(script_dir)
    core = collect_core(odoo_root, addons, modules)
    custom_recs = collect_custom(custom, modules)

    files = [Path(f) for f in args.files]
    if args.all_custom:
        files += [p for p in custom.rglob("*.xml") if "i18n" not in p.parts]
    if not files:
        parser.error("pass XML files or --all-custom")

    errors = 0
    checked = 0
    for cf in files:
        cf = cf.resolve() if cf.exists() else cf
        if not Path(cf).is_file():
            print(f"SKIP missing file {cf}")
            continue
        try:
            doc = etree.parse(str(cf))
        except Exception as exc:
            print(f"{cf}: XML parse failed: {exc}")
            errors += 1
            continue
        # module name: .../custom/<mod>/...
        cmod = "custom"
        parts = Path(cf).parts
        if "custom" in parts:
            cmod = parts[parts.index("custom") + 1]
        elif "odoo-custom" in parts:
            cmod = parts[parts.index("odoo-custom") + 1]
        for r in doc.iter("record"):
            if r.get("model") != "ir.ui.view":
                continue
            inh = r.find("field[@name='inherit_id']")
            if inh is None:
                continue
            ref = inh.get("ref")
            if not ref:
                continue
            checked += 1
            resolved = ref
            all_ids = set(core) | set(custom_recs)
            if ref not in all_ids and "." not in ref:
                if f"{cmod}.{ref}" in all_ids:
                    resolved = f"{cmod}.{ref}"
            if resolved not in core and resolved not in custom_recs:
                print(f"{cf}:{r.get('id')}: parent {ref} NOT FOUND in the 73-module Odoo 19 stack")
                print(f"    hint: {hint_for(ref, '')}")
                errors += 1
                continue
            skip = r.get("id") or ""
            skip_xid = skip if "." in skip else f"{cmod}.{skip}"
            base = combined(resolved, core, custom_recs, skip_xid=skip_xid)
            if base is None:
                print(f"{cf}:{r.get('id')}: could not build parent arch for {ref}")
                errors += 1
                continue
            arch = r.find("field[@name='arch']")
            missing = apply(etree.fromstring(etree.tostring(base)), arch)
            for expr, why in missing:
                print(f"{cf}:{r.get('id')} -> {ref}: MISSING {expr} ({why})")
                print(f"    hint: {hint_for(ref, expr)}")
                errors += 1

    print(f"xpath_check: {checked} inherited views, {errors} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
