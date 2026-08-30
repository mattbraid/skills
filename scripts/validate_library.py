#!/usr/bin/env python3
"""Validate the skills library's structure and manifests.

The library is one marketplace listing one plugin per category. This checks the
things that break an install but not a JSON parse: every category being listed,
its manifests agreeing, its skills actually being discoverable from that
category's plugin root, and SKILL.md files addressing their bundled scripts by a
${CLAUDE_PLUGIN_ROOT} path that really resolves.

Claude Code only. Pure stdlib, no vendor CLI required. Exits 1 on any error;
warnings don't fail.
"""

from __future__ import annotations  # keeps the annotations below valid on 3.9

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / ".claude-plugin" / "marketplace.json"

# A long description gets truncated in the skills list the model routes on,
# and the trigger words are what it loses first.
DESCRIPTION_WARN_CHARS = 700

# Support for these was removed deliberately; flag any that creep back in.
REMOVED_VENDOR_PATHS = (".codex-plugin", ".agents")

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_json(path: Path):
    if not path.exists():
        err(f"missing required file: {path.relative_to(ROOT)}")
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        err(f"{path.relative_to(ROOT)}: invalid JSON — {e}")
        return None


def parse_frontmatter(text: str):
    """Minimal YAML frontmatter reader: top-level `key: value` pairs only."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fields = {}
    key = None
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            fields[key] = m.group(2).strip()
        elif key and line.startswith((" ", "\t")):
            fields[key] += " " + line.strip()  # folded continuation
    return fields


def check_no_removed_vendors():
    for name in REMOVED_VENDOR_PATHS:
        for hit in ROOT.rglob(name):
            if ".git" in hit.parts:
                continue
            err(f"{hit.relative_to(ROOT)}: Codex/ChatGPT packaging was removed "
                "from this library; delete it or restore support deliberately")


def check_catalog():
    catalog = load_json(CATALOG)
    if catalog is None:
        return []
    if not isinstance(catalog.get("plugins"), list) or not catalog["plugins"]:
        err("marketplace.json: 'plugins' must be a non-empty array")
        return []
    if not catalog.get("name"):
        err("marketplace.json: no 'name'")
    if not catalog.get("owner"):
        err("marketplace.json: no 'owner'")

    entries = [p for p in catalog["plugins"] if isinstance(p, dict)]

    seen = set()
    for entry in entries:
        name = entry.get("name")
        if name in seen:
            err(f"marketplace.json: duplicate plugin name {name!r}")
        seen.add(name)

    # Every category directory must be listed, or its skills ship to nobody.
    listed = {(ROOT / e["source"]).resolve()
              for e in entries if isinstance(e.get("source"), str)}
    plugins_dir = ROOT / "plugins"
    if plugins_dir.is_dir():
        for child in sorted(plugins_dir.iterdir()):
            if child.is_dir() and child.resolve() not in listed:
                err(f"plugins/{child.name}/ exists but is not listed in "
                    "marketplace.json, so it can never be installed")
    return entries


def check_plugin(entry: dict):
    name = entry.get("name")
    if not name:
        err("marketplace.json: a plugin entry has no 'name'")
        return
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        err(f"plugin {name!r}: must be kebab-case — Claude Code accepts other "
            "forms but the claude.ai marketplace sync rejects them")
    source = entry.get("source")
    if not isinstance(source, str):
        warn(f"plugin '{name}': non-path source, skipping structural checks")
        return

    plugin_dir = (ROOT / source).resolve()
    if not plugin_dir.is_dir():
        err(f"plugin '{name}': source {source!r} does not exist")
        return

    manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
    manifest = load_json(manifest_path)
    if manifest is None:
        return

    if manifest.get("name") != name:
        err(f"plugin '{name}': .claude-plugin/plugin.json declares name "
            f"{manifest.get('name')!r}; it must match the catalog entry")
    if not manifest.get("description"):
        err(f"plugin '{name}': .claude-plugin/plugin.json has no description")
    if manifest.get("license") and not (ROOT / "LICENSE").exists():
        warn(f"plugin '{name}': a license is declared but there is no LICENSE file")

    cat_v, man_v = entry.get("version"), manifest.get("version")
    if cat_v != man_v:
        err(f"plugin '{name}': version mismatch — marketplace.json says "
            f"{cat_v!r}, plugin.json says {man_v!r}")
    if cat_v is None:
        warn(f"plugin '{name}': no version; Claude Code then resolves updates by "
             "commit SHA, so installers get every commit on the default branch")

    check_skills(name, plugin_dir, manifest)


def skill_dirs(name: str, plugin_dir: Path, manifest: dict):
    """Resolve where skills are discovered from, mirroring Claude Code.

    The default `skills/` directory is always scanned; a `skills` manifest field
    adds further directories, each of which *contains* skill directories.
    """
    roots = []
    default = plugin_dir / "skills"
    if default.is_dir():
        roots.append(default)

    declared = manifest.get("skills")
    if isinstance(declared, str):
        declared = [declared]
    if isinstance(declared, list):
        for rel in declared:
            path = (plugin_dir / rel).resolve()
            if not path.is_dir():
                err(f"plugin '{name}': skills path {rel!r} in plugin.json "
                    "does not exist")
                continue
            if (path / "SKILL.md").exists():
                err(f"plugin '{name}': skills path {rel!r} points at a single "
                    "skill; the field takes directories that *contain* skills")
                continue
            roots.append(path)
    elif declared is not None:
        err(f"plugin '{name}': 'skills' in plugin.json must be a string or array")

    return roots


def check_skills(name: str, plugin_dir: Path, manifest: dict):
    roots = skill_dirs(name, plugin_dir, manifest)
    root_skill = plugin_dir / "SKILL.md"

    if not roots:
        # Single-skill plugin: only valid with no skills/ dir and no manifest field.
        if root_skill.exists() and manifest.get("skills") is None:
            check_skill_md(name, plugin_dir, plugin_dir, root_skill)
        else:
            err(f"plugin '{name}': no skills/ directory, no usable 'skills' field, "
                "and no SKILL.md at the plugin root — nothing would be discovered")
        # Still check for skills shipped outside any discovery root: a root
        # SKILL.md makes the plugin "valid" while masking exactly that mistake.
        check_orphaned_skills(name, plugin_dir, roots, root_skill)
        return

    if root_skill.exists():
        warn(f"plugin '{name}': SKILL.md at the plugin root is ignored because "
             "skills are discovered from a directory; delete it to avoid confusion")

    found = 0
    for root in roots:
        for child in sorted(root.iterdir()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.exists():
                nested = list(child.rglob("SKILL.md"))
                rel = child.relative_to(plugin_dir)
                if nested:
                    err(f"plugin '{name}': {rel}/ has no SKILL.md but contains "
                        f"{len(nested)} nested one(s) — a skills directory must "
                        "be flat (<dir>/<name>/SKILL.md)")
                else:
                    err(f"plugin '{name}': {rel}/ has no SKILL.md")
                continue
            found += 1
            check_skill_md(name, plugin_dir, child, skill_md)

    if not found:
        warn(f"plugin '{name}': no skills found under "
             f"{[str(r.relative_to(plugin_dir)) for r in roots]}")

    check_orphaned_skills(name, plugin_dir, roots, root_skill)


def check_orphaned_skills(name: str, plugin_dir: Path, roots, root_skill: Path):
    """Find SKILL.md files that ship with the plugin but are never discovered.

    This is the failure that looks like success: the files are in the repo and
    in the install, so nothing is obviously missing, but Claude only scans the
    discovery roots and the skill silently never loads.
    """
    discovered = {r.resolve() for r in roots}
    for skill_md in sorted(plugin_dir.rglob("SKILL.md")):
        if ".git" in skill_md.parts:
            continue
        if skill_md == root_skill:
            continue
        # Discovered iff its parent directory sits directly in a discovery root.
        if skill_md.parent.parent.resolve() in discovered:
            continue
        err(f"plugin '{name}': {skill_md.relative_to(plugin_dir)} ships with the "
            "plugin but is outside every skills directory, so it is never "
            "discovered — move it under skills/ or add its parent to the "
            "'skills' field in plugin.json")


def check_skill_md(plugin: str, plugin_dir: Path, skill_dir: Path, skill_md: Path):
    rel = skill_md.relative_to(ROOT)
    text = skill_md.read_text()
    fm = parse_frontmatter(text)
    if fm is None:
        err(f"{rel}: no YAML frontmatter")
        return

    name = fm.get("name")
    if not name:
        err(f"{rel}: frontmatter has no 'name'")
    elif skill_dir != plugin_dir and name != skill_dir.name:
        err(f"{rel}: frontmatter name {name!r} does not match directory "
            f"{skill_dir.name!r} — the mismatch changes the invocation name")

    description = fm.get("description")
    if not description:
        err(f"{rel}: frontmatter has no 'description' — without one the model "
            "has nothing to route on")
    elif len(description) > DESCRIPTION_WARN_CHARS:
        warn(f"{rel}: description is {len(description)} chars; over "
             f"~{DESCRIPTION_WARN_CHARS} risks truncation in the skills list")

    body = text[text.find("\n---", 3) + 4:]

    # Regression guard: bare relative script invocations resolve against the
    # user's working directory once installed, not the skill directory.
    for m in re.finditer(r"^\s*(?:python3?|node|bash|sh)\s+(?!['\"]?\$\{)"
                         r"['\"]?((?:scripts|references|assets)/[^\s'\"]+)",
                         body, re.MULTILINE):
        err(f"{rel}: relative path {m.group(1)!r} in a command — address bundled "
            "files as ${CLAUDE_PLUGIN_ROOT}/... instead")

    # Every plugin-root-relative path referenced must actually resolve. This is
    # what catches a skill being moved without its SKILL.md being updated.
    for m in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s'\"`)]+)", body):
        if not (plugin_dir / m.group(1)).exists():
            err(f"{rel}: references ${{CLAUDE_PLUGIN_ROOT}}/{m.group(1)} "
                "which does not exist relative to the plugin root")


def main() -> int:
    check_no_removed_vendors()
    plugins = check_catalog()
    for entry in plugins:
        check_plugin(entry)

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")

    if errors:
        print(f"\n✘ {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    plural = "" if len(plugins) == 1 else "s"
    print(f"\n✔ {len(plugins)} plugin{plural} valid, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
