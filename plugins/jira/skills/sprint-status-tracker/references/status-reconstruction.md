# Reconstructing a day-by-day status timeline

The goal is a per-ticket, per-day status value for every reported day of the
sprint week. There are two ways to get one: read it off a snapshot that was
actually taken that day (observed), or infer it from timestamps and comments
when no snapshot covers that day (inferred). Always prefer the former —
inference is a fallback for gaps in the snapshot history, not the default
method.

> **Hard rule: a ticket is never dropped from the grid. DO NOT omit it.**
> Every ticket key that appears in *any* attached snapshot gets a row,
> covering the *entire* reported window, full stop — including a ticket that
> left the sprint on day one of the window. When a ticket is no longer in
> scope, its status becomes the literal string `"Removed"` for the
> subsequent days (see rule 1.7 below); the row itself never goes away, and
> its earlier days keep their real observed/inferred status. Writing a good
> footnote sentence about a removal is a supplement to this, never a
> substitute for it — "I mentioned it in the footnote" is not a reason a
> ticket's row can be missing from the grid. If you catch yourself reasoning
> that leaving a row out is cleaner or avoids clutter, that reasoning is
> wrong; stop and put the row back with a `"Removed"` status instead. Before
> rendering, verify this mechanically rather than trusting memory — see the
> verification step at the end of this section.

## Step 0: Gather, identify, and order the attached snapshots

This skill has no storage of its own — the snapshot history for a run is
exactly the set of Jira XML/RSS exports attached to the request, nothing
more and nothing less. There's no project file search and no naming
convention to follow: everything needed to identify and order a snapshot
lives inside the export itself.

1. **Parse every attached export**, one call per file:
   ```bash
   python scripts/parse_jira_xml.py <snapshot.xml> <snapshot-tickets.json>
   ```
   Each run also prints "Export generated at: ..." to stderr when the
   comment is present in the XML — capture that for every file.
2. **Resolve the sprint identity from the data, not the filename.** Read the
   `sprint` field off any ticket in each parsed file (the Jira "Sprint"
   custom field carries the full canonical name, e.g.
   `Pre-SAT Remediation #1 (10/08)`). All attached exports should agree on
   this value. If they don't, stop and flag it to the user — that usually
   means an export from the wrong sprint got attached by mistake, and
   guessing which one is right would silently corrupt the reconstruction.
   If the invocation also named a sprint (e.g. "Remediation #1"), treat that
   as a sanity check against the parsed value rather than the source of
   truth; if every file's `sprint` field is blank, fall back to asking.
3. **Order the snapshots chronologically using each export's own
   "Export generated at" timestamp** — never the attachment's filename or
   upload order, which tell you nothing reliable. The date portion of that
   timestamp is the sprint day that snapshot represents. If an export has no
   such comment, ask the user which day it was captured rather than
   guessing.
4. **If two exports land on the same calendar day**, treat the later one as
   that day's ground truth and the earlier as superseded — don't average or
   pick arbitrarily between them.
5. **Coverage will usually be partial.** A sprint week has five days; the
   attached set might cover all of them, a subset, or just one. That's
   expected and exactly what Steps 1–2 below are for — don't ask the user to
   go find more exports before proceeding unless nothing usable was attached
   at all.

## Step 1: Use the snapshot history

With every attached snapshot parsed, identified, and chronologically
ordered per Step 0, work through each ticket and each day of the sprint
week:

1. **A day with one or more snapshots taken on it** → use the ticket's
   status as of the *last* snapshot captured that day. This is ground truth,
   not a guess: whatever the export said, that's what the tracker shows.
2. **A day with no snapshot of its own, sitting between two days that do
   have snapshots** → you know the ticket's status at both ends of the gap.
   If it's the same status at both ends, the gap day is that status too —
   nothing to infer. If it changed across the gap, you know a transition
   happened somewhere in that window but not exactly when; apply the
   heuristic in Step 2, but *bounded* by those two known values rather than
   guessing freely from scratch.
3. **A day after the most recent snapshot** (i.e. today hasn't been
   snapshotted yet) → there's no later data point to bound against. Fall
   back fully to Step 2 against the latest snapshot's timestamps and
   comments.
4. **A day before the earliest snapshot** (common early in a sprint, before
   snapshot cadence catches up — e.g. the sprint's Monday and Tuesday when
   the first snapshot wasn't taken until Wednesday) → same situation as #3
   but running backward: there's no earlier data point either, so fall back
   fully to Step 2 against the *earliest* snapshot's timestamps and
   comments instead. This is exactly what the skill did before it tracked
   snapshot history at all, and it's still the right tool for this gap.
5. **A ticket not yet part of the tracked sprint's scope on a given day** →
   that cell doesn't exist; use `null` in `status_by_day` rather than
   inventing a status or backfilling one (see `scripts/render_tracker.py`,
   which renders `null` as the same dashed placeholder used for unreported
   future days). Don't anchor this purely to the ticket's Jira `created`
   date — a ticket can have been created well before the sprint and still
   only join *this* sprint's scope partway through (pulled from backlog,
   reprioritized in). The real anchor is whichever is later: the `created`
   date, or the first day any attached snapshot actually shows the ticket
   in this sprint. If a ticket's `created` date falls inside the reported
   window but it's already present in the earliest attached snapshot, trust
   the snapshot — it's ground truth that the ticket was already in scope.
6. **A newly-added ticket's first day in scope** → don't leave it blank and
   don't invent a backstory. Start it with whichever status is available or
   can be inferred, using the normal Step 1/Step 2 rules — same as any other
   day, just with the "clock" starting at first appearance instead of at the
   sprint's first day. If the day it's added has a snapshot of its own,
   that's ground truth (Step 1.1); if not, bound it the same way any other
   gap gets bounded (Step 1.2).
7. **A ticket present in an earlier snapshot but absent from a later one** →
   **DO NOT drop its row from the grid.** The row stays for the entire
   reported window regardless of what happens to the ticket. What changes
   is its *status*, not its presence: keep the ticket's real (observed or
   inferred) status for the days it was genuinely in the sprint, then apply
   one of the three cases below for the days after it disappears. Carrying
   its last real status forward unchanged would be wrong (that would claim
   it's still, say, "Blocked" when it may no longer even be in scope) — but
   the fix for that is switching its status to `"Removed"`, never removing
   the row.
   - **A nearby comment explains the removal** (e.g. descoping, sprint
     reprioritization) → this is ground truth. From the day it disappears
     onward, set its status to the literal string `"Removed"` (add it via
     `status_colors` in the render spec, since it's not one of the built-in
     workflow statuses), and use the comment as footnote material,
     generalized per the footnote-writing guidance below. The footnote is
     in addition to the row, not instead of it.
   - **No comment, but the last known status was terminal** (Released,
     Done, Resolved, Closed) → carry that terminal status forward instead
     of switching to `"Removed"`. Tickets very commonly roll off an "active
     sprint" export once complete — that's an artifact of the export scope,
     not a real disappearance, and nothing further will happen to a
     completed ticket anyway.
   - **No comment, and the last known status was non-terminal** → this is
     genuinely unexplained by the data. Don't guess at a resolution you
     can't evidence. Still set it to `"Removed"` from that day forward
     (it's factually true that it's no longer in the tracked scope), but
     flag this specific ticket in your reply as unexplained — it's worth
     the user checking with the team before this goes external, since
     `"Removed"` could be masking anything from a mundane data-scope change
     to a real problem.

## Verify no ticket was dropped

Before rendering — not after, since it's cheap to fix now and easy to miss
in a visual review of a dense grid — check mechanically that every ticket
key seen in any parsed snapshot made it into your spec:

```python
import json

all_keys = set()
for f in ["snapshot-a.json", "snapshot-b.json"]:  # every file you parsed
    all_keys.update(t["key"] for t in json.load(open(f)))

spec = json.load(open("spec.json"))
spec_keys = {t["key"] for g in spec["groups"] for t in g["tickets"]}

missing = all_keys - spec_keys
assert not missing, f"Dropped tickets, add them back: {missing}"
```

If this raises, that's a ticket that appeared in the sprint's real data and
isn't in your spec — go find it and add its row back (with a `"Removed"`
status for whichever days it was actually gone) rather than adjusting the
check. This is exactly the failure mode rule 1.7 exists to prevent, and it's
happened in practice: a run once explained a removal in the footnote and
left the ticket's row out of the grid entirely, reasoning that the footnote
covered it. It didn't — the footnote is prose the reader might skim past;
the grid is the record. Don't repeat that mistake.

Keep a mental (or literal) note of which cells came from step 1.1 (observed)
versus 1.2–1.4 (inferred) versus 1.5/1.6 (`null`, not yet in scope) versus
1.7 (`"Removed"`, with or without a documented reason), so you can tell the
user honestly what portion of the grid is a real record versus a
reconstruction — in your reply, not necessarily on the tracker itself. A
sprint with frequent snapshots should end up almost entirely observed; a
sprint with only one or two snapshots will lean heavily on inference, same
as before this skill tracked history at all.

If any single export happens to contain a genuine changelog (some Jira
instances / export configurations do include `<changelog>` or per-field
history), that's ground truth too and beats both snapshot-diffing and
inference — check for it before falling back to either.

## Step 2: Infer, bounded by whatever you do know

This is the same heuristic as before, just now scoped to actual gaps rather
than being asked to cover a whole week from a single export:

1. **If `updated` falls on the day in question**, it's reasonable to assume
   the status reached by then was reached that day — use it as that day's
   value. A comment discussing a hand-off, blocker, or "moving to QA" near
   the `updated` timestamp is good supporting evidence.
2. **If there's no update signal for that day**, carry forward the most
   recent known status (whether observed or already-inferred) rather than
   guessing at an intermediate one. The honest default is "nothing changed."
2a. **Special case: inferring backward into a day before the earliest
    snapshot, for a ticket created on that same day.** Don't reflexively
    carry the earliest snapshot's status backward — check whether that
    snapshot's `updated` timestamp actually falls on the day you're
    inferring. If it does, the status is well-evidenced (the transition
    happened that day, same as rule 1). If the earliest snapshot's `updated`
    falls on a *later* day, that status probably hadn't been reached yet on
    the creation day — the ticket was more likely still sitting at whatever
    a newly created ticket in this project normally starts at. Cross-check
    against other tickets created the same day whose earliest snapshot *is*
    updated that day: their shared starting status (usually "To Do" or
    equivalent) is a stronger inference than mechanically carrying a
    several-stages-later status backward. This distinction matters — in
    testing, several tickets created Monday but not updated again until
    Tuesday were sitting at "In Progress" or further by Tuesday morning;
    naively carrying that back would have shown a full day of progress that
    hadn't happened yet.
3. **A single `updated` timestamp often has to cover multiple real
   transitions** (e.g. To Do → In Progress → In Review all before the next
   comment). When you can't distinguish sub-day movement, collapse it to the
   status you can actually evidence — don't invent intermediate stops you
   have no signal for.
4. **When bounded by two known snapshot values** (Step 1.2), don't infer a
   status outside that pair unless you have real evidence of a third state
   passed through — most gaps resolve to "changed sometime in here," not a
   multi-hop journey.
5. **Comments are your best source of qualitative color** even when they
   don't move status — e.g. "who's picking this up?" threads, or a note that
   an item is being proposed for descoping. These are worth surfacing in the
   footnote narrative (in a positive, generalized way — see below) even
   though they don't change any cell in the grid.

## Grouping tickets into workstreams

The grid reads much better grouped (Data Migration, Bug Fixes, Blocked items,
etc.) than as one flat list of 20+ rows. Infer groups from what's actually in
the data:

- Ticket type (Task vs Bug) is a weak signal on its own, but combined with
  title patterns it's often enough — e.g. a run of tickets all titled
  "Migration: <thing>" or all referencing the same underlying epic/parent
  clearly belong together.
- A shared prefix or reference code in the title (like the `T101`, `T104`
  markers in `references/spec-example.json`) often marks tickets driven by the
  same underlying test or site issue.
- Explicit issue links (blocks / is blocked by / relates to) between tickets
  in the set are strong evidence they belong in the same group, especially
  chains like "A blocks B, C, D, E."
- A status that's structurally different from the rest of the sprint (e.g.
  several tickets sitting Blocked against the same external dependency) is
  worth its own group — it reads as a distinct story ("here's what's stuck
  and why") rather than getting lost in a long list.

If the tickets are genuinely heterogeneous with no clear pattern (e.g. a
grab-bag backlog grooming sprint with no thematic links), don't force
groups that don't exist — ask the user how they'd like it split, or fall back
to a single flat group rather than inventing a false narrative structure.

## Writing the footnote

The footnote is the one piece of this tracker aimed squarely at a client or
stakeholder audience who isn't in the internal Slack/standup conversations.
Keep it to one short paragraph and:

- Lead with the positive, concrete evidence of movement — an item released,
  bugs that moved into QA/Review, work started across every open thread.
  Real numbers and ticket movement are more convincing than adjectives.
- Reframe blockers constructively — "being actively worked through to confirm
  priority" rather than silence, but also don't overclaim resolution that
  hasn't happened yet.
- Never surface internal back-and-forth by name or in detail (who asked whom
  to pick something up, disagreements about scope, etc.) — that's exactly the
  kind of internal-conversation noise this tracker exists to filter out for
  an external audience. Generalize it: "a couple of items are being reviewed
  for descoping in line with upstream reprioritisation" is enough.
- Close by noting the cadence (e.g. "refreshed daily through Friday") so the
  reader understands this is a living document, not a one-off snapshot.
