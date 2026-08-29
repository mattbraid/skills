---
name: sprint-status-tracker
description: Build a one-page, client-facing sprint status tracker — the day-by-day status-progression grid — from Jira XML/RSS export snapshots attached to the request. Use for a sprint status grid, ticket status progression, or "how did tickets move this week". Reconstructs each day from the attached snapshot history, diffing between snapshots by each export's own generation timestamp and inferring only for days no export covers. Nothing is persisted between runs, so refreshing means re-attaching an updated set. Not for a prose narrative report or a raw data dump.
---

# Sprint status tracker

> **Paths.** Bundled scripts and references are addressed from the plugin root:
> `${CLAUDE_PLUGIN_ROOT}/skills/sprint-status-tracker/`. The commands below spell
> that out in full because the working directory is the user's project, not this
> skill. Inline mentions of `references/…` below are relative to this skill's own
> directory.

Turns a sprint's attached Jira XML export snapshots into a single
printable page that shows, at a glance, how every ticket moved through its
statuses across a Monday–Friday week — plus a short, positive footnote
written for someone outside the team (a client or stakeholder) who only sees
this snapshot, not the day-to-day Slack/standup chatter behind it.

This skill is invoked by attaching the Jira XML/RSS export snapshots that
should feed the tracker — however many the user has for the sprint week,
from one up to five — directly to the request. There's no external storage
to check and nothing to file afterward: the attached set *is* the input,
full stop. If the user wants the tracker refreshed later in the week, that
means running the skill again with an updated set of attachments, not
expecting it to remember anything from last time. It's not a general Jira
reporting tool, and it's not the right choice for a prose narrative report
(no visual grid, no footnote) or for a raw data dump (that's the `xlsx`
skill's job).

## Why this is more than "make an HTML table"

A few things about this task are easy to get wrong if you improvise from
scratch each time, which is exactly why this skill bundles scripts and
reference docs for them:

1. **A single Jira XML export has no changelog.** One export gives you only
   *current* status plus `created`/`updated` timestamps and comments — no
   record of "status changed from A to B on date D." But when the user
   attaches several dated exports for the same sprint, two snapshots taken
   on different days *do* give you ground truth: whatever changed between
   them, changed. Treat that attached history as the primary source, and
   only fall back to inference for the gaps it doesn't cover — see
   `references/status-reconstruction.md`.
2. **Which day a snapshot represents has to come from the export itself, not
   the attachment.** Attachment order and filenames aren't reliable —
   Jira's XML carries its own generation timestamp, and that's what
   identifies both the sprint day a snapshot captures and the order multiple
   snapshots go in. Getting this wrong silently shuffles the whole
   reconstruction. See Step 0 of `references/status-reconstruction.md`.
3. **Fitting a real ticket list onto one printable page takes iteration.**
   The CSS in `scripts/render_tracker.py` was tuned across several passes to
   get ~22 tickets across 4 groups onto one A4-landscape page without
   shrinking to illegibility. Reuse it rather than re-deriving font sizes and
   padding from scratch — and still verify the actual output (see
   `references/one-page-fit.md`), since every dataset is a little different.
4. **A ticket leaving the sprint is not a reason to drop its row.** This has
   gone wrong in practice: a run once explained a removal in the footnote
   and left the ticket out of the grid entirely, reasoning that the
   footnote already covered it. It didn't, and the grid was left
   incomplete. Every ticket key that appears in any attached snapshot gets
   a row for the whole reported window — a ticket that leaves gets a
   `"Removed"` status, never an absent row. See the hard-rule callout and
   the mechanical verification step in `references/status-reconstruction.md`
   before you render.

## Workflow

1. **Gather every export attached to this request.** That's the entire
   input — if only one is attached, that's fine, the reconstruction just
   leans more on inference; if the user mentions a sprint name but attached
   nothing, ask them to attach the exports rather than trying to proceed
   without data.

2. **Parse every attached export, then identify and order them.**
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/sprint-status-tracker/scripts/parse_jira_xml.py" <snapshot.xml> <snapshot-tickets.json>
   ```
   Run this once per attached file. Follow Step 0 of
   `references/status-reconstruction.md` to resolve the sprint's identity
   from the parsed `sprint` field (flagging any mismatch across files rather
   than guessing) and to order the snapshots using each export's own
   generation timestamp — not filenames or attachment order.

3. **Reconstruct each ticket's status for each reported day — history first,
   inference only for the gaps.**
   Follow Steps 1–2 of `references/status-reconstruction.md`. In short: a
   day covered by an attached snapshot gets that snapshot's status, no
   guessing involved; a day sitting in a gap between two snapshots gets the
   inference heuristic bounded by what you know at both ends; and any day
   outside the attached range entirely — before the earliest snapshot, or
   after the most recent one — falls back to the full inference heuristic
   against the nearest snapshot's timestamps/comments. Sprint membership
   also isn't static: tickets can join or leave mid-week. A ticket not yet
   in scope gets `null` (not a guessed status) for the days before it
   appears, then starts from whatever's available once it does; a ticket
   that disappears from a later snapshot keeps its real status for the days
   it was actually there, then switches to `"Removed"` — see Step 1 of
   `references/status-reconstruction.md` for the full treatment, including
   when to flag a disappearance as unexplained. Keep track of which cells
   are observed vs inferred so you can be honest with the user about it (in
   your reply, not necessarily on the tracker itself).

4. **Group tickets into workstreams.**
   Infer sensible groups from ticket titles, types, shared reference codes,
   epics, or issue-link chains — see the grouping section of
   `references/status-reconstruction.md`. If the set is genuinely a grab-bag
   with no thematic structure, ask the user how they'd like it split rather
   than inventing false groupings.

5. **Write the footnote.**
   One short paragraph, positive and specific, written for someone outside
   the team. See the footnote-writing guidance in
   `references/status-reconstruction.md` — the short version: lead with
   concrete movement, reframe blockers constructively, never name internal
   back-and-forth, close with the refresh cadence.

6. **Assemble the spec and render.**
   Build a JSON spec matching `references/spec-example.json` (a full worked
   example from a real sprint). Each ticket's `priority` is a narrow third
   column (after the item title, before the owner) — lift it straight from
   the `priority` field `scripts/parse_jira_xml.py` already extracts from
   the Jira export, don't reconstruct or infer it the way status is
   reconstructed. Before rendering, run the verification check in "Verify
   no ticket was dropped" in `references/status-reconstruction.md` —
   confirm every ticket key seen in any parsed snapshot has a row in your
   spec. Then render:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/sprint-status-tracker/scripts/render_tracker.py" spec.json output.html
   ```
   The script computes the summary stacked-bar chart and totals directly
   from your per-ticket data — don't hand-type percentages or counts
   anywhere, let the script derive them so the summary can never drift out
   of sync with the grid.

7. **Verify it's actually one clean page.**
   Follow `references/one-page-fit.md`. Run its preflight check first —
   Playwright and poppler are present in some environments and not others, and
   the reference gives you the branch to take for each. Where they're
   available: render to PDF, check the page count, and *look at* the resulting
   image — don't just trust a page count of 1. Where they aren't, say the fit
   is unverified rather than implying it passed.

8. **Deliver it, and be clear about what refreshing it later requires.**
   Send the HTML file to the user. Since nothing from this run is persisted
   anywhere, mention that refreshing the tracker later means invoking the
   skill again with an updated set of attached exports (the earlier ones
   plus whatever's new) — not that it'll pick up where this run left off on
   its own. You can still offer to persist *this run's output* as an
   updatable artifact rather than a one-off file, so edits within the same
   conversation don't require a full re-send.

## A note on scope

If the user wants a written day-by-day narrative (prose, not a grid) instead
of or in addition to this tracker, that's a plain document — build it
directly with the `docx` skill if they want a Word file, no special handling
needed. This skill is specifically for the one-page visual status-progression
grid.
