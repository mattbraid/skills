# Skills Library

A personal library of AI agent skills, packaged so they can be installed from this git URL into **Claude Code** and **ChatGPT / Codex**.

## Install

### Claude Code

```shell
/plugin marketplace add mattbraid/skills
/plugin install jira@skills-library
```

Claude Code periodically runs `git pull` on the marketplace clone in the background, so you pick up new releases automatically. To pull immediately:

```shell
/plugin marketplace update skills-library
```

Pin to a release instead of tracking `main` with `/plugin marketplace add mattbraid/skills@v1.0.0`.

### ChatGPT / Codex

```shell
codex plugin marketplace add mattbraid/skills
codex plugin add jira@skills-library
```

Once the marketplace is added, the plugin also appears in ChatGPT's Plugins directory on web, desktop and mobile. There is no background auto-update on this side — re-run `codex plugin marketplace update skills-library` to pull new releases, and restart the session to pick up the changes.

## What is a Skill?

A **skill** is a directory with a `SKILL.md` at its root: YAML frontmatter (`name` and a `description` that says *when* to use it) plus a Markdown body holding the workflow. Optional `scripts/` and `references/` sit alongside. The body loads only when the skill is actually used, so long reference material is cheap.

This is the [Agent Skills](https://code.claude.com/docs/en/skills) format, which both Claude and ChatGPT/Codex read. The per-platform difference is only in the plugin manifests that wrap the skills for distribution — the skills themselves are identical.

## Repository Structure

```
skills/
├── .claude-plugin/
│   └── marketplace.json              # Catalog — Claude Code
├── .agents/plugins/
│   └── marketplace.json              # Catalog — ChatGPT / Codex
├── plugins/
│   └── jira/                         # One plugin per category
│       ├── .claude-plugin/plugin.json
│       ├── .codex-plugin/plugin.json
│       └── skills/                   # Flat: skills/<name>/SKILL.md
│           ├── sprint-status-tracker/
│           │   ├── SKILL.md
│           │   ├── scripts/
│           │   └── references/
│           └── defect-lifecycle-tracker/
│               ├── SKILL.md
│               ├── scripts/
│               └── references/
├── templates/TEMPLATE.md
└── INDEX.md
```

Two things about this layout are load-bearing:

- **`skills/` must be flat.** Both platforms discover skills at `skills/<name>/SKILL.md` and no deeper. Categories are expressed as *plugins*, not as folders inside `skills/` — which also lets people install `jira` without taking everything else.
- **Everything except the four manifests is shared.** Supporting both ecosystems costs two catalog files and two plugin manifests; the skills, scripts and references have exactly one copy.

## Skills

### jira

Both Jira skills work the same way: attach a Jira XML/RSS export to the request, get back a one-page A4-landscape HTML report. Nothing is persisted between runs — refreshing means running again with a newer export. They're complementary rather than alternatives: one shows *movement over a week*, the other shows *where the work sits right now*.

#### [sprint-status-tracker](plugins/jira/skills/sprint-status-tracker/SKILL.md)

A client-facing sprint status grid showing how every ticket moved through its statuses across a Monday–Friday week, plus a short stakeholder-facing footnote.

A single Jira export has no changelog — it only gives current status. So the skill takes *multiple* dated exports (one to five for the week), orders them by each export's own generation timestamp, and treats what changed between two snapshots as ground truth, falling back to inference only for days no export covers. Every ticket appearing in any snapshot keeps a row for the whole window; one that leaves the sprint gets a `"Removed"` status rather than disappearing.

- `scripts/parse_jira_xml.py` — one export → JSON
- `scripts/render_tracker.py` — spec JSON → the one-page HTML (derives all totals and the summary chart itself)
- `references/status-reconstruction.md` — snapshot ordering, status reconstruction, grouping, footnote guidance
- `references/one-page-fit.md` — how to verify the page actually fits

Use it for the visual status-progression grid. Not for a prose narrative report, and not for a raw data dump.

#### [defect-lifecycle-tracker](plugins/jira/skills/defect-lifecycle-tracker/SKILL.md)

A client-facing defect flow page from a **single** export: a KPI strip (total open, % in backlog, P1–P5 with threshold highlighting), one card per lifecycle phase (Backlog, Analysis, Development, Customer Testing), a deferred-items panel, and a 30-day intake heatmap.

The organising principle is that the page reports **aggregates, not tickets**. Two behaviours are deliberate and worth knowing up front: the renderer *refuses to render* on a status it can't map to a phase (a silent default would produce a page that looks right and is wrong), and a priority excluded by the export's JQL is greyed as "excluded by query" rather than shown as a clean zero.

- `scripts/render_defect_flow.py` — parse and render; `--print-stats` inspects the counts without drawing anything
- `scripts/config.example.json` — phase mappings, priority thresholds, heatmap window, titles
- `references/lifecycle-mapping.md` — what each status means and why it maps where it does
- `references/one-page-fit.md` — verifying the fit and which CSS knobs to turn

Use it for status/phase breakdowns and "where is the work sitting" questions. Not for per-ticket detail (that's a spreadsheet) and not for day-by-day progression (that's `sprint-status-tracker`).

## Adding a Skill

### To an existing plugin

1. Create `plugins/<plugin>/skills/<skill-name>/SKILL.md`.
2. Give it frontmatter with `name` and a `description` that says both what it does and **when to use it**. That description is all the model sees when deciding whether to load the skill, so front-load the trigger phrasings and name the near-misses it should *not* handle. Keep it tight — Codex budgets the whole skills list to 2% of the context window and truncates long descriptions.
3. Keep the body a workflow: numbered steps and the commands to run. Push anything long into `references/` and executable code into `scripts/`, so `SKILL.md` stays short enough to read on every invocation.
4. **Address bundled files from the plugin root**, e.g. `${CLAUDE_PLUGIN_ROOT}/skills/<skill-name>/scripts/foo.py`. Once installed, the working directory is the user's project, so relative paths resolve to nothing.
5. Add a row to [INDEX.md](INDEX.md) and bump the plugin `version`.

### A new category

1. `mkdir -p plugins/<category>/skills` and add both manifests (copy `plugins/jira/.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`).
2. Register it in the `plugins` array of **both** catalog files.
3. Validate before pushing (see below).

## Validating

```bash
python3 scripts/validate_library.py
```

Checks the things that break an install but not a JSON parse: the two catalogs
listing the same plugins, versions agreeing across all four manifests, `skills/`
being flat, frontmatter present with a matching `name`, and — the two mistakes
most likely to recur — no bare relative script paths in a `SKILL.md`, and every
`${CLAUDE_PLUGIN_ROOT}/…` path actually resolving. Pure stdlib, no vendor CLI.

[CI](.github/workflows/validate.yml) runs this on every push and PR, byte-compiles
the bundled scripts, and additionally runs `claude plugin validate` (non-gating,
so a PR never fails on npm being unreachable). To run the vendor check yourself:

```bash
claude plugin validate .
claude plugin validate ./plugins/<category>
```

## Releasing

Both `plugin.json` files carry a `version`. **Bump it on every release.** Without a version, Claude Code resolves updates by commit SHA and installed users get every commit on `main`, half-finished ones included. With one, they move between tagged releases.

## Index

See [INDEX.md](INDEX.md) for the full list of skills.

## License

[MIT](LICENSE).
