---
name: defect-lifecycle-tracker
description: Build a one-page, client-facing defect flow visualisation from a single Jira XML/RSS export attached to the request. Use for defect flow, defect pipeline, bug dashboard, status or phase breakdown, delivery lifecycle view, pre-SAT position, "where is the work sitting", or "how many are still in backlog" — even without the words "one-pager". Shows aggregate counts by lifecycle phase (Backlog, Analysis, Development, Customer Testing), a P1–P5 KPI strip with threshold highlighting, a deferred-items panel, and a 30-day intake heatmap. Not for per-ticket detail (that's a spreadsheet) or day-by-day sprint progression (that's sprint-status-tracker).
---

# Defect lifecycle tracker

> **Paths.** Bundled scripts and references are addressed from the plugin root:
> `${CLAUDE_PLUGIN_ROOT}/skills/defect-lifecycle-tracker/`. The commands below
> spell that out in full because the working directory is the user's project, not
> this skill. Inline mentions of `references/…` below are relative to this skill's
> own directory.

Turns one attached Jira XML export into a single A4-landscape page showing how
many defects sit at each stage of delivery. The audience is a client or
stakeholder reading a status pack — someone who needs the shape of the backlog
in ten seconds, not a ticket list.

**The organising principle: this page reports aggregates, not tickets.** Every
design decision follows from that. Individual keys appear in exactly one place
(the deferred panel, and only while there are few enough to name), because a
parked item is a decision someone owes rather than a number. If a request wants
per-ticket rows, that's the `xlsx` skill's job, not this one.

## Workflow

1. **Take the attached export.** One Jira XML/RSS file is the whole input. If
   the user describes a project but attaches nothing, ask for the export rather
   than proceeding — there is nothing to infer from.

2. **Inspect before rendering.**
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/defect-lifecycle-tracker/scripts/render_defect_flow.py" <export.xml> --print-stats
   ```
   This parses the export and prints the counts it would draw, rendering
   nothing. Read the status list. Two things to check: every status is mapped
   (the script errors out if not — see step 3), and the phase totals look
   plausible for what the user described. This is also where you'll see
   `priorities_filtered_by_jql`, which matters for step 5.

3. **Resolve any unmapped status.** The script refuses to render when it meets
   a status it doesn't know, and names it. This is deliberate: an unmapped
   status quietly defaulting into "Deferred" would produce a page that looks
   correct and is wrong, and nothing on its face would reveal it. Read
   `references/lifecycle-mapping.md` for how each status earns its phase, then
   add the mapping to a config file. When the semantics genuinely aren't
   obvious from the status name, ask the user rather than guessing — they know
   their workflow and you don't.

4. **Render, then verify the page.**
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/defect-lifecycle-tracker/scripts/render_defect_flow.py" <export.xml> out.html [--title "..."] [--config cfg.json]
   ```
   **Pass a title the user gave you.** If the request named the report — "build
   me a defect lifecycle tracker for the Q3 pre-SAT position", "…called Release
   4.2 Defect Position" — pass that through with `--title`. It's the reader's
   own name for the thing and it beats anything derivable from the export. With
   no title from anywhere the page reads "Defect Pipeline", which is honest but
   anonymous; if the user didn't offer one and the context makes an obvious
   title available (a release name, a milestone, a project they've been
   discussing), suggest it rather than shipping the bare default.
   Then follow `references/one-page-fit.md`, starting with its preflight check —
   Playwright and poppler are present in some environments and not others, and
   the reference gives you the branch to take for each. Where they're available:
   render to PDF, confirm `Pages: 1`, and *look at the image*. A page count of 1
   doesn't catch a label that truncated or a legend that wrapped — both have
   happened, and both are invisible in the count. Where they aren't, say the fit
   is unverified rather than implying it passed.

5. **Report the caveats in your reply, not just on the page.** The page carries
   the source note; your message should say plainly what the reader can and
   can't conclude. In particular:
   - **A filtered priority is not a zero.** If the JQL contains a priority
     clause (e.g. `priority >= 2`), the excluded tiles show 0 because the query
     never asked for them. The page greys these and labels them "excluded by
     query", and you should say so too — "P1: 0" read as an all-clear is the
     most consequential misreading this page can produce.
   - **Empty statuses are a finding.** If every Customer Testing item sits in
     Waiting For Upgrade and the QA statuses are all zero, work is queued for
     deployment but not being tested. Say that; it's the sort of thing the grid
     shows and the reader skims past.
   - **One export means no history.** Counts are a snapshot. Nothing on this
     page implies movement between phases, and you shouldn't narrate it as
     though it does.

6. **Deliver the HTML and the PDF.** Refreshing later means running the skill
   again with a newer export — nothing is persisted between runs.

## What goes on the page

Four bands, top to bottom. Keep this structure; it's what the layout is tuned for.

The masthead carries the small "Defect Lifecycle Tracker" eyebrow above the
report title, so the page identifies what it is even when the title is specific
to one release or milestone.

- **KPI strip** — total open defects, % still in backlog, then P1–P5. A
  priority tile highlights red when its count exceeds its threshold (default
  P1 >0, P2 >0, P3 >20, P4 >50, P5 >80). Priority totals **exclude Customer
  Testing** by default, on the reasoning that those items are built and
  awaiting verification rather than work still to deliver — the caption under
  the strip states the basis and the count excluded, because a P2 of 12 and a
  P2 of 18 are different numbers to put in front of a steering group and the
  reader deserves to know which they're looking at.
- **Where the work is sitting** — one card per phase with the headline count,
  share of total, priority-mix bar, the occupied sub-statuses with proportional
  bars, and any unoccupied ones greyed out.
- **Deferred** — items outside the flow (Blocked by client, Waiting for
  Re-Occurrence). Named individually up to `deferred_detail_max` (default 6),
  aggregated by status beyond that.
- **Intake heatmap** — GitHub-contribution style, weeks as rows and Mon–Sun as
  columns. Transposed from GitHub's orientation because a 5×7 grid is short and
  wide, which is what a landscape panel has room for.

Everything is computed in the renderer from the export. Don't hand-type a count,
percentage or date into the HTML — the whole point of deriving them in one place
is that the KPI strip can't drift away from the phase cards.

## Configuration

All keys optional; see
`${CLAUDE_PLUGIN_ROOT}/skills/defect-lifecycle-tracker/scripts/config.example.json`.

| Key | Purpose |
|---|---|
| `phase_of` | Map statuses to phases; merged over the defaults. The one you'll reach for most. |
| `priority_thresholds` | Per-priority highlight trigger. |
| `priority_exclude_phases` | Phases left out of the P1–P5 totals. `[]` to count everything. |
| `heat_days` | Heatmap window, default 30. |
| `deferred_detail_max` | Above this many deferred items, aggregate instead of naming. |
| `report_title` | The main heading. Overridden by `--title`; defaults to "Defect Pipeline". |
| `subtitle`, `eyebrow`, `as_of`, `footnote` | Presentation overrides. `eyebrow` defaults to "Defect Lifecycle Tracker"; `as_of` to the export's own generation timestamp. |

## Reference files

- `references/lifecycle-mapping.md` — what each status means and why it maps
  where it does. Read this before adding any mapping.
- `references/one-page-fit.md` — how to verify the one-page fit, and which CSS
  knobs to turn (in what order) when a dataset overflows.
