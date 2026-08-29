#!/usr/bin/env python3
"""Validate the skills library's structure and manifests.

Checks the things that break an install but not a JSON parse: the two catalogs
agreeing, versions matching across all four manifests, skills/ being flat, and
SKILL.md files addressing their bundled scripts from the plugin root rather than
relative to a working directory that won't exist once installed.

Pure stdlib, no vendor CLI required. Exits 1 on any error; warnings don't fail.
"""

from __future__ import annotations  # keeps the annotations below valid on 3.9

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_CATALOG = ROOT / ".claude-plugin" / "marketplace.json"
CODEX_CATALOG = ROOT / ".agents" / "plugins" / "marketplace.json"

# Codex budgets the whole skills list to 2% of context (8000 chars when unknown)
# and truncates descriptions to fit. Long ones lose their trigger words first.
DESCRIPTION_WARN_CHARS = 700

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


def parse_frontmatter(text: str) -> dict | None:
    """Minimal YAML frontmatter reader: top-level `key: value` pairs only."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fields: dict[str, str] = {}
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


def check_catalogs():
    claude = load_json(CLAUDE_CATALOG)
    codex = load_json(CODEX_CATALOG)
    if claude is None or codex is None:
        return {}

    entries = {}
    for label, cat in (("claude", claude), ("codex", codex)):
        if not isinstance(cat.get("plugins"), list):
            err(f"{label} catalog: 'plugins' must be an array")
            continue
        entries[label] = {p.get("name"): p for p in cat["plugins"] if p.get("name")}

    if len(entries) == 2:
        only_claude = entries["claude"].keys() - entries["codex"].keys()
        only_codex = entries["codex"].keys() - entries["claude"].keys()
        for name in sorted(only_claude):
            err(f"plugin '{name}' is in the Claude catalog but not the Codex one")
        for name in sorted(only_codex):
            err(f"plugin '{name}' is in the Codex catalog but not the Claude one")
        for name in sorted(entries["claude"].keys() & entries["codex"].keys()):
            cv = entries["claude"][name].get("version")
            xv = entries["codex"][name].get("version")
            if cv != xv:
                err(f"plugin '{name}': catalog versions disagree "
                    f"(claude={cv!r}, codex={xv!r})")

    return entries.get("claude", {})


def check_plugin(name: str, entry: dict):
    source = entry.get("source")
    if not isinstance(source, str):
        warn(f"plugin '{name}': non-path source, skipping structural checks")
        return
    plugin_dir = (ROOT / source).resolve()
    if not plugin_dir.is_dir():
        err(f"plugin '{name}': source {source} does not exist")
        return

    versions = {"catalog": entry.get("version")}
    for label, rel in (("claude", ".claude-plugin/plugin.json"),
                       ("codex", ".codex-plugin/plugin.json")):
        manifest = load_json(plugin_dir / rel)
        if manifest is None:
            continue
        versions[label] = manifest.get("version")
        if manifest.get("name") != name:
            err(f"plugin '{name}': {rel} declares name "
                f"{manifest.get('name')!r}, expected {name!r}")
        if not manifest.get("description"):
            err(f"plugin '{name}': {rel} has no description")
        if manifest.get("license") and not (ROOT / "LICENSE").exists():
            warn(f"plugin '{name}': {rel} declares a license but "
                 "there is no LICENSE file at the repo root")

    distinct = {v for v in versions.values() if v is not None}
    if len(distinct) > 1:
        err(f"plugin '{name}': version mismatch across manifests — {versions}")
    if None in versions.values():
        warn(f"plugin '{name}': a manifest has no version; installers will "
             "resolve updates by commit SHA, so users get every commit")

    check_skills(name, plugin_dir)


def check_skills(plugin: str, plugin_dir: Path):
    skills_dir = plugin_dir / "skills"
    if not skills_dir.is_dir():
        if not (plugin_dir / "SKILL.md").exists():
            err(f"plugin '{plugin}': no skills/ directory and no root SKILL.md")
        return

    found = False
    for child in sorted(skills_dir.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        found = True
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            # A directory here with no SKILL.md is the classic nesting mistake:
            # a category folder that discovery will scan and silently skip.
            nested = [p for p in child.rglob("SKILL.md")]
            if nested:
                err(f"plugin '{plugin}': skills/{child.name}/ has no SKILL.md but "
                    f"contains {len(nested)} nested one(s) — skills/ must be flat "
                    "(skills/<name>/SKILL.md)")
            else:
                err(f"plugin '{plugin}': skills/{child.name}/ has no SKILL.md")
            continue
        check_skill_md(plugin, plugin_dir, child, skill_md)

    if not found:
        warn(f"plugin '{plugin}': skills/ is empty")


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
    elif name != skill_dir.name:
        err(f"{rel}: frontmatter name {name!r} does not match directory "
            f"{skill_dir.name!r} — the mismatch changes the invocation name")

    description = fm.get("description")
    if not description:
        err(f"{rel}: frontmatter has no 'description' — without one the model "
            "has nothing to route on")
    elif len(description) > DESCRIPTION_WARN_CHARS:
        warn(f"{rel}: description is {len(description)} chars; over "
             f"~{DESCRIPTION_WARN_CHARS} risks truncation in Codex's skills list")

    body = text[text.find("\n---", 3) + 4:]

    # Regression guard: bare relative script invocations resolve against the
    # user's working directory once installed, not the skill directory.
    for m in re.finditer(r"^\s*(?:python3?|node|bash|sh)\s+(?!['\"]?\$\{)"
                         r"['\"]?((?:scripts|references|assets)/[^\s'\"]+)",
                         body, re.MULTILINE):
        err(f"{rel}: relative path {m.group(1)!r} in a command — address bundled "
            "files as ${CLAUDE_PLUGIN_ROOT}/skills/<name>/... instead")

    # Every plugin-root-relative path referenced must actually exist.
    for m in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s'\"`)]+)", body):
        target = plugin_dir / m.group(1)
        if not target.exists():
            err(f"{rel}: references ${{CLAUDE_PLUGIN_ROOT}}/{m.group(1)} "
                "which does not exist")


def main() -> int:
    catalog = check_catalogs()
    for name, entry in sorted(catalog.items()):
        check_plugin(name, entry)

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")

    plural = "" if len(catalog) == 1 else "s"
    if errors:
        print(f"\n✘ {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"\n✔ {len(catalog)} plugin{plural} valid, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
