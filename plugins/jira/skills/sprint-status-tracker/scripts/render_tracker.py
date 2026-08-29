#!/usr/bin/env python3
"""
Render a one-page HTML sprint status tracker from a JSON spec.

Usage:
    python render_tracker.py <spec.json> <output.html>

The spec format (see references/spec-example.json for a full worked example):

{
  "meta": {
    "eyebrow": "SPRINT PROGRESS TRACKER",
    "title": "Demo Product Delivery Plan (10/08)",
    "subtitle": "DEMO · Demo Delivery Plan",
    "week_label": "10–14 August 2026",
    "as_of": "Tue 11 Aug, 12:15"
  },
  "days": ["MON 10", "TUE 11", "WED 12", "THU 13", "FRI 14"],
  "reported_days": 2,
  "groups": [
    {
      "name": "Data Migration",
      "tickets": [
        {
          "key": "DEMO-22",
          "title": "Deploy & configure migration tools",
          "priority": "2",
          "owner": "Migration Lead",
          "story_points": 0.5,
          "status_by_day": ["Released", "Released"]
        }
      ]
    }
  ],
  "footnote": "One short, positive, client-safe paragraph."
}

Only supply real statuses for the first `reported_days` entries of
`status_by_day` on every ticket -- the remaining days (through the end of
`days`) are automatically rendered as dashed "not yet reported" placeholders,
and the top summary bar is computed from the real data, not hand-typed
percentages. This keeps the two in sync and avoids arithmetic mistakes.

A `status_by_day` entry within the reported range can be `null` instead of a
status string, for a day the ticket wasn't part of the tracked sprint scope
yet (created or added to the sprint partway through the week) -- it renders
with the same dashed placeholder as an unreported future day, and is left
out of that day's summary bar counts rather than being treated as a real
status. Every ticket still needs exactly `reported_days` entries total,
`null` or otherwise -- see references/status-reconstruction.md for when a
`null` is appropriate versus carrying a real inferred status.

A ticket's `priority` is lifted directly from its Jira `priority` field
(via `scripts/parse_jira_xml.py`) rather than reconstructed per day like
status -- it's a single static value per ticket, shown as its own narrow
column right after the item title. Omit the field (or leave it null) for a
ticket with no priority set and it renders as an empty cell.

Status colors are built in for the common Jira workflow states (To Do, In
Progress, In Review, In QA, Blocked, Released). If your ticket set uses
different status names, add a "status_colors" map to the spec, e.g.:

  "status_colors": { "Peer Review": "#2a5fa8", "Done": "#0f8a3c" }

Any status encountered that isn't in the built-in map or your override map
falls back to neutral grey and prints a warning to stderr -- so you'll notice
if a status name doesn't match (e.g. a typo) rather than have it silently
mis-colored.
"""
import sys
import json


DEFAULT_STATUS_COLORS = {
    "To Do": "#9aa1ab",
    "Open": "#9aa1ab",
    "Backlog": "#9aa1ab",
    "In Progress": "#5f97dd",
    "In Review": "#2a5fa8",
    "Peer Review": "#2a5fa8",
    "In QA": "#17427a",
    "Testing": "#17427a",
    "Blocked": "#c8393a",
    "On Hold": "#c8393a",
    "Released": "#0f8a3c",
    "Done": "#0f8a3c",
    "Closed": "#0f8a3c",
    "Resolved": "#0f8a3c",
}
FALLBACK_COLOR = "#7d848d"

CSS = """
  @page { size: A4 landscape; margin: 10mm; }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    font-family: -apple-system, "Segoe UI", Calibri, Helvetica, Arial, sans-serif;
    background: #f4f5f7;
    color: #1c1c1c;
  }
  .page {
    width: 277mm;
    min-height: 180mm;
    margin: 3mm auto;
    background: #ffffff;
    padding: 3mm 11mm 2mm 11mm;
    box-shadow: 0 1px 4px rgba(0,0,0,0.12);
  }
  .masthead {
    display: flex; justify-content: space-between; align-items: flex-end;
    border-bottom: 2.5px solid #1F3864; padding-bottom: 2px; margin-bottom: 3px;
  }
  .masthead .eyebrow {
    font-size: 9.5px; letter-spacing: 1.2px; font-weight: 700; color: #B08D57;
    text-transform: uppercase; margin-bottom: 2px;
  }
  .masthead h1 { font-size: 20px; margin: 0; color: #1F3864; font-weight: 800; letter-spacing: -0.2px; }
  .masthead .sub { font-size: 11px; color: #55606e; margin-top: 2px; }
  .masthead .asof { text-align: right; font-size: 10px; color: #55606e; line-height: 1.5; }
  .masthead .asof b { color: #1c1c1c; }
  .legend { display: flex; gap: 14px; align-items: center; margin: 3px 0 5px 0; flex-wrap: wrap; }
  .legend .item { display: flex; align-items: center; gap: 5px; font-size: 9.5px; color: #3a3f47; }
  .legend .swatch { width: 11px; height: 11px; border-radius: 3px; display: inline-block; flex-shrink: 0; }
  .legend .pending-swatch {
    width: 11px; height: 11px; border-radius: 3px; display: inline-block;
    border: 1.4px dashed #b7bcc4; background: #fbfbfc; flex-shrink: 0;
  }
  .flow { display: grid; gap: 8px; align-items: center; margin-bottom: 2px; }
  .flow .flabel { font-size: 9px; font-weight: 700; color: #55606e; text-transform: uppercase; letter-spacing: 0.4px; }
  .flow .day-label { font-size: 10px; font-weight: 700; color: #1F3864; text-align: center; margin-bottom: 3px; }
  .flow .day-col { display: flex; flex-direction: column; }
  .stackbar { height: 11px; border-radius: 3px; display: flex; overflow: hidden; background: #eef0f2; }
  .stackbar.pending {
    border: 1.4px dashed #c3c8d0;
    background: repeating-linear-gradient(135deg, #fbfbfc, #fbfbfc 5px, #f2f3f5 5px, #f2f3f5 10px);
  }
  .stackbar .seg { height: 100%; }
  .flow .count-caption { font-size: 8px; color: #8a919b; text-align: center; margin-top: 2px; }
  table.grid { width: 100%; border-collapse: collapse; margin-top: 4px; }
  table.grid col.key { width: 58px; }
  table.grid col.title { width: auto; }
  table.grid col.priority { width: 30px; }
  table.grid col.owner { width: 92px; }
  table.grid col.day { width: 84px; }
  .grp-row td {
    background: #1F3864; color: #ffffff; font-size: 9px; font-weight: 700;
    letter-spacing: 0.4px; text-transform: uppercase; padding: 1.5px 8px;
  }
  .head-row th {
    font-size: 8.5px; text-transform: uppercase; letter-spacing: 0.4px; color: #7d848d;
    font-weight: 700; text-align: center; padding: 2px 4px 1px 4px; border-bottom: 1px solid #dfe2e6;
  }
  .head-row th.left { text-align: left; padding-left: 8px; }
  tr.tkt td { padding: 0.3px 4px; border-bottom: 1px solid #eef0f2; font-size: 8.8px; vertical-align: middle; }
  tr.tkt:nth-child(even) td { background: #fafbfc; }
  tr.tkt td.key { font-weight: 700; color: #1F3864; padding-left: 8px; white-space: nowrap; font-size: 9px; }
  tr.tkt td.title { color: #2c313a; font-size: 9.3px; line-height: 1.25; }
  tr.tkt td.priority { color: #55606e; font-size: 8.7px; text-align: center; font-weight: 700; }
  tr.tkt td.owner { color: #6a7280; font-size: 8.7px; }
  .chip-wrap { display: flex; justify-content: center; }
  .chip {
    display: inline-block; min-width: 60px; text-align: center; font-size: 8px; font-weight: 700;
    letter-spacing: 0.15px; padding: 2.5px 4px; border-radius: 3px; color: #ffffff;
  }
  .chip.pending {
    min-width: 60px; text-align: center; font-size: 8px; font-weight: 600; padding: 2.5px 4px;
    border-radius: 3px; border: 1.3px dashed #c3c8d0; color: #a7adb6; background: #fbfbfc;
  }
  .footnote {
    margin-top: 2px; padding-top: 2px; border-top: 1px solid #dfe2e6;
    display: flex; gap: 10px; align-items: flex-start;
  }
  .footnote .mark { font-size: 15px; color: #B08D57; line-height: 1; margin-top: 1px; }
  .footnote p { margin: 0; font-size: 9.7px; line-height: 1.45; color: #454b54; font-style: italic; }
  .footnote p b { color: #1F3864; font-style: normal; }
"""


def esc(s):
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def color_for(status, overrides):
    if status in overrides:
        return overrides[status]
    if status in DEFAULT_STATUS_COLORS:
        return DEFAULT_STATUS_COLORS[status]
    print(f"WARNING: unrecognized status '{status}' -- falling back to grey. "
          f"Add it to spec.status_colors to control its color.", file=sys.stderr)
    return FALLBACK_COLOR


def build(spec):
    meta = spec["meta"]
    days = spec["days"]
    reported = spec["reported_days"]
    groups = spec["groups"]
    footnote = spec.get("footnote", "")
    overrides = spec.get("status_colors", {})

    all_tickets = [t for g in groups for t in g["tickets"]]
    for t in all_tickets:
        if len(t.get("status_by_day", [])) != reported:
            raise ValueError(
                f"Ticket {t.get('key')} has {len(t.get('status_by_day', []))} "
                f"status_by_day entries but reported_days={reported}. "
                f"Every ticket needs exactly one status per reported day."
            )

    total_items = len(all_tickets)
    total_points = sum(float(t["story_points"]) for t in all_tickets if t.get("story_points"))

    # legend: union of statuses actually used, in a stable common order first
    used_statuses = []
    seen = set()
    preferred_order = ["To Do", "In Progress", "In Review", "In QA", "Blocked", "Released"]
    for s in preferred_order:
        if any(s in t["status_by_day"] for t in all_tickets):
            used_statuses.append(s)
            seen.add(s)
    for t in all_tickets:
        for s in t["status_by_day"]:
            if s is None:
                continue
            if s not in seen:
                used_statuses.append(s)
                seen.add(s)

    legend_html = "".join(
        f'<div class="item"><span class="swatch" style="background:{color_for(s, overrides)}"></span>{esc(s)}</div>'
        for s in used_statuses
    )
    legend_html += '<div class="item"><span class="pending-swatch"></span>Not yet reported</div>'

    # flow summary: computed from actual data, not hand-typed
    flow_cols = []
    for day_idx, day_label in enumerate(days):
        if day_idx < reported:
            counts = {}
            for t in all_tickets:
                s = t["status_by_day"][day_idx]
                if s is None:
                    continue
                counts[s] = counts.get(s, 0) + 1
            segs = "".join(
                f'<div class="seg" style="width:{(count/total_items)*100:.2f}%;background:{color_for(s, overrides)}"></div>'
                for s, count in counts.items()
            )
            caption = " · ".join(f"{count} {s}" for s, count in counts.items())
            flow_cols.append(
                f'<div class="day-col"><div class="day-label">{esc(day_label)}</div>'
                f'<div class="stackbar">{segs}</div>'
                f'<div class="count-caption">{esc(caption)}</div></div>'
            )
        else:
            flow_cols.append(
                f'<div class="day-col"><div class="day-label">{esc(day_label)}</div>'
                f'<div class="stackbar pending"></div>'
                f'<div class="count-caption">to be updated</div></div>'
            )
    flow_html = (
        f'<div class="flow" style="grid-template-columns: 64px repeat({len(days)}, 1fr);">'
        f'<div class="flabel">Sprint&nbsp;flow</div>{"".join(flow_cols)}</div>'
    )

    # header row
    day_headers = "".join(f"<th>{esc(d)}</th>" for d in days)
    head_row = (
        f'<tr class="head-row"><th class="left">Ticket</th><th class="left">Item</th>'
        f'<th>Priority</th><th class="left">Owner</th>{day_headers}</tr>'
    )

    # column widths
    col_days = "".join('<col class="day">' for _ in days)
    colgroup = f'<col class="key"><col class="title"><col class="priority"><col class="owner">{col_days}'

    # group + ticket rows
    body_rows = []
    for g in groups:
        body_rows.append(f'<tr class="grp-row"><td colspan="{4 + len(days)}">{esc(g["name"])}</td></tr>')
        for t in g["tickets"]:
            cells = []
            for day_idx in range(len(days)):
                if day_idx < reported:
                    status = t["status_by_day"][day_idx]
                    if status is None:
                        cells.append('<td><div class="chip-wrap"><span class="chip pending">&mdash;</span></div></td>')
                    else:
                        c = color_for(status, overrides)
                        cells.append(f'<td><div class="chip-wrap"><span class="chip" style="background:{c}">{esc(status)}</span></div></td>')
                else:
                    cells.append('<td><div class="chip-wrap"><span class="chip pending">&mdash;</span></div></td>')
            body_rows.append(
                f'<tr class="tkt"><td class="key">{esc(t["key"])}</td>'
                f'<td class="title">{esc(t["title"])}</td>'
                f'<td class="priority">{esc(t.get("priority") or "")}</td>'
                f'<td class="owner">{esc(t.get("owner", "Unassigned"))}</td>'
                f'{"".join(cells)}</tr>'
            )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{esc(meta['title'])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
  <div class="masthead">
    <div>
      <div class="eyebrow">{esc(meta.get('eyebrow', 'SPRINT PROGRESS TRACKER'))}</div>
      <h1>{esc(meta['title'])}</h1>
      <div class="sub">{esc(meta.get('subtitle', ''))}</div>
    </div>
    <div class="asof">
      Week of <b>{esc(meta.get('week_label', ''))}</b><br>
      Data current as of <b>{esc(meta.get('as_of', ''))}</b><br>
      {total_items} items &middot; {total_points:g} story points
    </div>
  </div>
  <div class="legend">{legend_html}</div>
  {flow_html}
  <table class="grid">
    <colgroup>{colgroup}</colgroup>
    {head_row}
    {"".join(body_rows)}
  </table>
  <div class="footnote">
    <div class="mark">&#10077;</div>
    <p>{footnote}</p>
  </div>
</div>
</body>
</html>
"""
    return html


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    spec_path, out_path = sys.argv[1], sys.argv[2]
    with open(spec_path) as f:
        spec = json.load(f)
    html = build(spec)
    with open(out_path, "w") as f:
        f.write(html)
    n_tickets = sum(len(g["tickets"]) for g in spec["groups"])
    print(f"Wrote {out_path} ({n_tickets} tickets, {len(spec['groups'])} groups, "
          f"{spec['reported_days']}/{len(spec['days'])} days reported)", file=sys.stderr)
    if n_tickets > 26:
        print(f"NOTE: {n_tickets} tickets is more than this template was tuned for (~22-24 "
              f"fits one A4-landscape page at readable size). Render to PDF and check the page "
              f"count -- see references/one-page-fit.md for how to tighten it further, or "
              f"whether to split into two pages instead.", file=sys.stderr)


if __name__ == "__main__":
    main()
