# Skills Library

A personal library of agent skills for **Claude Code**, installable from this git URL as a plugin.

## Install

```shell
/plugin marketplace add mattbraid/skills
/plugin install mattbraid-skills@skills-library
```

Claude Code periodically runs `git pull` on the marketplace clone in the background, so new releases arrive automatically. To pull immediately:

```shell
/plugin marketplace update skills-library
```

Pin to a release instead of tracking `main` with `/plugin marketplace add mattbraid/skills@v1.0.2`.

Check what a version actually registered:

```shell
claude plugin details mattbraid-skills@skills-library
```

That prints the component inventory. If a skill you expected isn't in the list, it wasn't discovered — see [Structure](#structure).

## What is a Skill?

A skill is a directory with a `SKILL.md` at its root: YAML frontmatter (`name`, and a `description` that says *when* to use it) plus a Markdown body holding the workflow. Optional `scripts/` and `references/` sit alongside. The body loads only when the skill is used, so long reference material is cheap.

## Structure

The repository **is** the plugin — `marketplace.json` lists one plugin whose `source` is `./`, and both manifests live in `.claude-plugin/`.

```
skills/
├── .claude-plugin/
│   ├── marketplace.json          # catalog: one plugin, source "./"
│   └── plugin.json               # the plugin manifest
├── skills/                       # discovery root — must be flat
│   ├── sprint-status-tracker/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── references/
│   └── defect-lifecycle-tracker/
│       ├── SKILL.md
│       ├── scripts/
│       └── references/
├── scripts/validate_library.py
├── templates/TEMPLATE.md
└── INDEX.md
```

Three rules decide whether a skill is actually discovered — get one wrong and the plugin installs cleanly while loading nothing:

- **`skills/` at the plugin root is the discovery root, and it must be flat.** Claude scans `skills/<name>/SKILL.md` and no deeper. A skill nested any further — under a category folder, say — ships with the plugin and is silently never loaded.
- **A `skills` field in `plugin.json` takes directories that *contain* skills**, not paths to individual skill directories. This library omits the field and relies on the default.
- **A `SKILL.md` at the plugin root is only loaded when there is no `skills/` directory and no `skills` field.** Otherwise it is ignored — and it will happily mask the fact that nothing else was found.

`scripts/validate_library.py` enforces all three.

## Skills

Both skills work the same way: attach a Jira XML/RSS export to the request, get back a one-page A4-landscape HTML report. Nothing is persisted between runs — refreshing means running again with a newer export. They're complementary rather than alternatives: one shows *movement over a week*, the other shows *where the work sits right now*.

### [sprint-status-tracker](skills/sprint-status-tracker/SKILL.md)

A client-facing sprint status grid showing how every ticket moved through its statuses across a Monday–Friday week, plus a short stakeholder-facing footnote.

A single Jira export has no changelog — it only gives current status. So the skill takes *multiple* dated exports (one to five for the week), orders them by each export's own generation timestamp, and treats what changed between two snapshots as ground truth, falling back to inference only for days no export covers. Every ticket appearing in any snapshot keeps a row for the whole window; one that leaves the sprint gets a `"Removed"` status rather than disappearing.

- `scripts/parse_jira_xml.py` — one export → JSON
- `scripts/render_tracker.py` — spec JSON → the one-page HTML (derives all totals and the summary chart itself)
- `references/status-reconstruction.md` — snapshot ordering, status reconstruction, grouping, footnote guidance
- `references/one-page-fit.md` — how to verify the page actually fits

Use it for the visual status-progression grid. Not for a prose narrative report, and not for a raw data dump.

### [defect-lifecycle-tracker](skills/defect-lifecycle-tracker/SKILL.md)

A client-facing defect flow page from a **single** export: a KPI strip (total open, % in backlog, P1–P5 with threshold highlighting), one card per lifecycle phase (Backlog, Analysis, Development, Customer Testing), a deferred-items panel, and a 30-day intake heatmap.

The organising principle is that the page reports **aggregates, not tickets**. Two behaviours are deliberate and worth knowing up front: the renderer *refuses to render* on a status it can't map to a phase (a silent default would produce a page that looks right and is wrong), and a priority excluded by the export's JQL is greyed as "excluded by query" rather than shown as a clean zero.

- `scripts/render_defect_flow.py` — parse and render; `--print-stats` inspects the counts without drawing anything
- `scripts/config.example.json` — phase mappings, priority thresholds, heatmap window, titles
- `references/lifecycle-mapping.md` — what each status means and why it maps where it does
- `references/one-page-fit.md` — verifying the fit and which CSS knobs to turn

Use it for status/phase breakdowns and "where is the work sitting" questions. Not for per-ticket detail (that's a spreadsheet) and not for day-by-day progression (that's `sprint-status-tracker`).

## Adding a Skill

1. Create `skills/<skill-name>/SKILL.md` — directly under `skills/`, not nested any deeper.
2. Give it frontmatter with `name` (matching the directory) and a `description` that says both what it does and **when to use it**. That description is all the model sees when deciding whether to load the skill, so front-load the trigger phrasings and name the near-misses it should *not* handle.
3. Keep the body a workflow: numbered steps and the commands to run. Push anything long into `references/` and executable code into `scripts/`, so `SKILL.md` stays short enough to read on every invocation.
4. **Address bundled files as `${CLAUDE_PLUGIN_ROOT}/skills/<skill-name>/…`.** Once installed the working directory is the user's project, so relative paths resolve to nothing.
5. Add a row to [INDEX.md](INDEX.md) and bump the version in **both** manifests.

## Validating

```bash
python3 scripts/validate_library.py
```

Checks what breaks an install but not a JSON parse: the two manifests agreeing on name and version, every shipped `SKILL.md` actually sitting inside a discovery root, frontmatter present with a matching `name`, no bare relative script paths, and every `${CLAUDE_PLUGIN_ROOT}/…` path resolving. Pure stdlib, no vendor CLI.

[CI](.github/workflows/validate.yml) runs it on every push and PR, byte-compiles the bundled scripts, and additionally runs `claude plugin validate` (non-gating, so a PR never fails on npm being unreachable).

## Releasing

Both manifests carry a `version`, and they must match. **Bump on every release** — without a version change an installed copy will not pick the new one up, and with no version at all Claude Code resolves updates by commit SHA so installers get every commit on `main`.

## License

[MIT](LICENSE).
