# Status → lifecycle phase

The page has four phases plus a deferred bucket. Every status in the export
must land in exactly one of them, and the renderer refuses to draw the page
until they all do.

## Why an unmapped status is a hard error

The obvious implementation gives unmapped statuses a default bucket and prints
a warning. That's the wrong trade here. A miscategorised status doesn't look
broken — the page still renders, the numbers still add to the total, and the
column it lands in still looks reasonable. The reader has no way to tell, and
neither does the person who ran the skill unless they happened to read stderr.
Refusing to render costs one round trip; a silently wrong page gets forwarded
to a client. So the script names the offending statuses and stops.

When a status name doesn't make its phase obvious, ask the user. They know
whether "Awaiting Merge" sits before or after peer review in their workflow;
you're guessing from the string.

## The phases

### Backlog — `Open`
Raised and triaged into the queue, but not started. This drives the "% still in
backlog" KPI, which is usually the headline number on the page: it separates an
intake problem from a throughput problem.

### Analysis — `For Analysis`
Needs elaboration, refinement, or a steer from the client to confirm a
requirement. Work is happening, but it's not build work.

Note the boundary with Deferred: an item *being analysed* is in the flow; an
item *waiting on the client to act* is not. `Blocked by client` is deferred for
that reason, even though it often sits adjacent to analysis in practice.

### Development — the SDLC statuses
`Selected For Dev`, `In Build/Development`, `Development Done`, `Peer Review`,
`Blocked`, `Ready for Test`, `Test in Progress`, `Testing Blocked`.

This is the standard build-and-internal-test cycle. `Blocked` (as distinct from
`Blocked by client`) is an internal impediment, so it stays inside the
development column rather than being pulled out — it's the team's to clear.

Some tickets are marked `Done` at the end of this cycle when there's no need to
re-test in the customer's environment. Done items are normally outside the
export's JQL anyway; if they appear, decide with the user whether the page
should show a completed column at all — the default layout doesn't have one,
because it reports open work.

### Customer Testing — `Waiting For Upgrade`, `In Customer QA`, `Customer QA Failed`, `Reopened`
Items that cleared the SDLC and are queued for deployment to the customer
environment, or being verified there. Verified items move to `Done`; failures
come back as `Reopened`.

Two readings worth surfacing when you see them:
- **All in `Waiting For Upgrade`, QA statuses empty** — built and queued, but no
  customer testing is actually happening. Often a deployment cadence problem
  rather than a defect problem.
- **`Reopened` or `Customer QA Failed` climbing** — fixes aren't holding in the
  customer environment, which is a different and worse problem than a large
  backlog.

### Deferred — `Blocked by client`, `Waiting for Re-Occurrence`
Parked outside the flow, waiting on an external trigger.

- `Blocked by client` — dependent on client action to proceed.
- `Waiting for Re-Occurrence` — not reliably reproducible, parked for follow-up.

These get their own panel rather than a phase card because they aren't
progressing and shouldn't be read as work-in-flight. They're also the only
place individual ticket keys appear on the page: each one represents a decision
someone owes, and a bare count doesn't prompt anyone to make it.

## Priority totals and the Customer Testing exclusion

By default, the P1–P5 tiles count only items **not** in Customer Testing. The
reasoning: those items are built, and what remains is verification, so counting
them as priority-weighted work still to deliver overstates the load.

This changes the numbers materially — on the export this skill was built
against, P2 read 18 including Customer Testing and 12 excluding it. Neither is
wrong, but they answer different questions, so the page always states which
basis it's using and how many items were excluded. Set
`priority_exclude_phases: []` to count everything.

## Priorities filtered out by the JQL

The renderer scans the export's own JQL for a priority clause and greys any
tile the query excluded, labelling it "excluded by query" instead of showing a
bare 0.

This matters because `priority >= 2` is a common filter and it removes P1
entirely. A P1 tile reading 0 looks like an all-clear and isn't one.

**The comparison semantics are an assumption.** Jira orders priorities by their
position in the priority scheme, not by the numeral in the name. In the exports
this was built against the names *are* the numerals 1–5 and `priority >= 2`
returned 2, 3, 4 and 5 — so the script treats the comparison numerically on the
name. If a project uses named priorities (Highest/High/Medium) or a scheme
whose order doesn't match the numerals, the detection may mislabel a tile.
Treat the flag as a prompt to check the JQL yourself, not as ground truth.
