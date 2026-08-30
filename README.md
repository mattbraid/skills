# Skills Library

A personal library of agent skills for **Claude Code**, installable from this git URL as a plugin.

## Install

Add the marketplace once, then install the categories you want on this machine:

```shell
/plugin marketplace add mattbraid/skills
/plugin install jira@skills-library
```

Each category is a separate plugin, so a machine only carries the skills it needs. That matters at scale: every installed skill's description sits in the context of **every** session (~250 tokens each), whether or not you use it that day.

Claude Code periodically runs `git pull` on the marketplace clone in the background, so new releases arrive automatically. To pull immediately:

```shell
/plugin marketplace update skills-library
```

Pin to a release instead of tracking `main` with `/plugin marketplace add mattbraid/skills@v1.0.2`.

Check what a version actually registered:

```shell
claude plugin details jira@skills-library
```

That prints the component inventory. If a skill you expected isn't in the list, it wasn't discovered — see [Structure](#structure).

## What is a Skill?

A skill is a directory with a `SKILL.md` at its root: YAML frontmatter (`name`, and a `description` that says *when* to use it) plus a Markdown body holding the workflow. Optional `scripts/` and `references/` sit alongside. The body loads only when the skill is used, so long reference material is cheap.

## Structure

**One marketplace, one plugin per category.** The category is the unit of installation, which is what keeps the library expandable: a hundred skills across a dozen categories still means each machine carries only the two or three categories it uses.

```
skills/
├── .claude-plugin/
│   └── marketplace.json          # the catalog — lists every category
├── plugins/
│   └── jira/                     # a category = an installable plugin
│       ├── .claude-plugin/
│       │   └── plugin.json
│       └── skills/               # discovery root — must be flat
│           ├── sprint-status-tracker/
│           │   ├── SKILL.md
│           │   ├── scripts/
│           │   └── references/
│           └── defect-lifecycle-tracker/
│               ├── SKILL.md
│               ├── scripts/
│               └── references/
├── templates/category/           # copy this to start a new category
├── scripts/validate_library.py
└── INDEX.md
```

Categories live in `plugins/`; skills live in `skills/` **inside a category**. That second level is the one that trips people up, because Claude Code's discovery rules are stricter than they look:

- **`skills/` at a plugin's root is the discovery root, and it must be flat.** Claude scans `skills/<name>/SKILL.md` and no deeper. A skill nested any further — under a category folder *inside* `skills/`, say — ships with the plugin and is silently never loaded. Categories are expressed as separate plugins precisely because they cannot be expressed as folders here.
- **A `skills` field in `plugin.json` takes directories that *contain* skills**, not paths to individual skill directories. This library omits the field and relies on the default.
- **A `SKILL.md` at a plugin root is only loaded when there is no `skills/` directory and no `skills` field.** Otherwise it is ignored — and it will happily mask the fact that nothing else was found.

`scripts/validate_library.py` enforces all three, plus the category-level rules below.

## Skills

### jira

`/plugin install jira@skills-library`

Both skills work the same way: attach a Jira XML/RSS export to the request, get back a one-page A4-landscape HTML report. Nothing is persisted between runs — refreshing means running again with a newer export. They're complementary rather than alternatives: one shows *movement over a week*, the other shows *where the work sits right now*.

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

## Adding a Skill to an existing category

1. Create `plugins/<category>/skills/<skill-name>/SKILL.md` — directly under that category's `skills/`, not nested any deeper.
2. Give it frontmatter with `name` (matching the directory) and a `description` that says both what it does and **when to use it**. That description is all the model sees when deciding whether to load the skill, so front-load the trigger phrasings and name the near-misses it should *not* handle.
3. Keep the body a workflow: numbered steps and the commands to run. Push anything long into `references/` and executable code into `scripts/`, so `SKILL.md` stays short enough to read on every invocation.
4. **Address bundled files as `${CLAUDE_PLUGIN_ROOT}/skills/<skill-name>/…`.** `CLAUDE_PLUGIN_ROOT` is the *category's* root, not the repo's. Once installed the working directory is the user's project, so relative paths resolve to nothing.
5. Add a row to [INDEX.md](INDEX.md) and bump that category's version in **both** its `plugin.json` and its `marketplace.json` entry.

## Adding a Category

```bash
cp -R templates/category plugins/<category>
```

Then edit exactly two things:

1. `plugins/<category>/.claude-plugin/plugin.json` — set `name` (kebab-case, matching the directory) and `description`.
2. `.claude-plugin/marketplace.json` — add an entry:
   ```json
   {
     "name": "<category>",
     "source": "./plugins/<category>",
     "version": "1.0.0",
     "description": "One line on what this category's skills do."
   }
   ```

Rename `skills/example-skill/` to your first real skill and validate. A category that exists on disk but is missing from `marketplace.json` can never be installed, so the validator treats that as an error rather than letting it pass quietly.

Categories are independent: each carries its own version and is released by bumping that version alone.

## Validating

```bash
python3 scripts/validate_library.py
```

Checks what breaks an install but not a JSON parse:

- every directory in `plugins/` is listed in `marketplace.json` — an unlisted category can never be installed
- each category's two manifests agree on name and version, and names are kebab-case (the claude.ai marketplace sync rejects anything else)
- every shipped `SKILL.md` sits inside a discovery root — one that doesn't is packaged, installed, and never loaded
- frontmatter is present with a `name` matching its directory
- no bare relative script paths, and every `${CLAUDE_PLUGIN_ROOT}/…` path resolves

Pure stdlib, no vendor CLI.

[CI](.github/workflows/validate.yml) runs it on every push and PR, byte-compiles the bundled scripts, and additionally runs `claude plugin validate` (non-gating, so a PR never fails on npm being unreachable).

## Releasing

Each category carries a `version` in its `plugin.json` and in its `marketplace.json` entry, and the two must match. **Bump on every release** — without a version change an installed copy will not pick the new one up, and with no version at all Claude Code resolves updates by commit SHA so installers get every commit on `main`.

## License

[MIT](LICENSE).
