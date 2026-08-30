#!/usr/bin/env python3
"""
Render a one-page defect-lifecycle flow view from a single Jira XML/RSS export.

Usage:
    python render_defect_flow.py <export.xml> <output.html> [--config config.json] [--title "..."]
    python render_defect_flow.py <export.xml> --print-stats     # inspect, render nothing

Everything on the page -- the KPI strip, the phase cards, the heatmap, the
footnote -- is computed here from the export. Nothing is hand-typed, so the
figures cannot drift out of sync with each other or with the source data.

The script reads three things out of the export that matter beyond the issues
themselves:
  * JIRA's own generation timestamp (the leading XML comment) -> the "as at"
    stamp and the anchor date for the 30-day heatmap.
  * The JQL in the channel <link> -> printed verbatim in the source note, and
    scanned for a priority clause so the page can flag priorities the query
    filtered out rather than presenting a filtered zero as a real zero.
  * Every distinct status -> mapped to a lifecycle phase. An unmapped status
    is a hard error, never a silent default; see references/lifecycle-mapping.md.

The report title comes from --title if given (use it to pass a title the user
supplied when invoking the skill), else "report_title" in the config, else the
neutral default "Defect Pipeline".

See config.example.json for the override file. All keys are optional.
"""
import sys, os, json, re, html, collections, email.utils
import datetime as dt
import urllib.parse
import xml.etree.ElementTree as ET

# --------------------------------------------------------------- defaults ---
# The lifecycle. Order matters: it is the order the phases appear on the page.
PHASES = ["Backlog", "Analysis", "Development", "Customer Testing"]
DEFERRED = "Deferred"

DEFAULT_PHASE_OF = {
    "Open":                       "Backlog",
    "For Analysis":               "Analysis",
    "Selected For Dev":           "Development",
    "In Build/Development":       "Development",
    "Development Done":           "Development",
    "Peer review":                "Development",
    "Blocked":                    "Development",
    "Ready for Test":             "Development",
    "Test in Progress":           "Development",
    "Testing Blocked":            "Development",
    "Waiting For Upgrade":        "Customer Testing",
    "In Customer QA":             "Customer Testing",
    "Customer QA Failed":         "Customer Testing",
    "Reopened":                   "Customer Testing",
    "Blocked by client":          DEFERRED,
    "Waiting for Re-Occurrence":  DEFERRED,
}
# Workflow order, used to sequence the sub-status rows inside each phase card.
DEFAULT_STATUS_ORDER = list(DEFAULT_PHASE_OF)

DEFAULT_CONFIG = {
    "eyebrow": "Defect Lifecycle Tracker",
    "report_title": None,        # default: "Defect Pipeline"; --title wins over this
    "title": None,               # deprecated alias for report_title
    "subtitle": None,            # default: derived from the projects present
    "as_of": None,               # default: the export's generation timestamp
    "phase_of": {},              # merged over DEFAULT_PHASE_OF
    "status_order": None,        # default: DEFAULT_STATUS_ORDER
    "priority_thresholds": {"1": 0, "2": 0, "3": 20, "4": 50, "5": 80},
    "priority_exclude_phases": ["Customer Testing"],
    "heat_days": 30,
    "deferred_detail_max": 6,    # above this, the deferred panel aggregates
    "footnote": None,            # default: generated
}

PHASE_BLURB = {
    "Backlog": "Raised, not yet started",
    "Analysis": "Elaboration / client steer",
    "Development": "Build, review &amp; internal test",
    "Customer Testing": "Deploy &amp; verify in customer env",
}
PHASE_COLOR = {
    "Backlog": "#8B93A0", "Analysis": "#C08A2E", "Development": "#2F6FBF",
    "Customer Testing": "#17827A", DEFERRED: "#B23A3A",
}
PRIOS = ["1", "2", "3", "4", "5"]
PRIO_COLOR = {"1": "#8E1B12", "2": "#C8393A", "3": "#E0A32E",
              "4": "#6F9BD1", "5": "#AEB6C0"}
HEAT_SHADES = ["#eceef1", "#c7dcf2", "#8ab4e0", "#4a7fc1", "#1F3864"]
SHORT_STATUS = {"Customer QA Failed": "QA Failed", "In Build/Development": "In Build"}


# ------------------------------------------------------------------ parse ---
def strip_html(s):
    if s is None:
        return None
    return re.sub(r"<[^<]+?>", "", html.unescape(s)).strip()


def txt(el, path):
    f = el.find(path)
    return f.text if f is not None else None


def parse_export(path):
    """Return (issues, meta) from a Jira XML/RSS export."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    root = ET.fromstring(raw)
    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else root.findall(".//item")

    issues = []
    for it in items:
        assignee = it.find("assignee")
        issues.append({
            "key": txt(it, "key"),
            "summary": strip_html(txt(it, "summary")),
            "type": txt(it, "type"),
            "status": txt(it, "status"),
            "priority": txt(it, "priority"),
            "assignee": assignee.text if assignee is not None and assignee.text else "Unassigned",
            "created": txt(it, "created"),
            "updated": txt(it, "updated"),
            "project": (txt(it, "key") or "-").split("-")[0],
        })

    m = re.search(r"RSS generated by JIRA.*?\bat\s+(.+?UTC\s+\d{4})", raw)
    generated_at = None
    if m:
        try:
            generated_at = dt.datetime.strptime(
                m.group(1), "%a %b %d %H:%M:%S UTC %Y").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass

    jql = None
    link = txt(channel, "link") if channel is not None else None
    if link and "jql=" in link:
        jql = urllib.parse.unquote_plus(link.split("jql=", 1)[1])
        jql = re.split(r"\s+ORDER\s+BY\s+", jql, flags=re.I)[0].strip()

    return issues, {"generated_at": generated_at, "jql": jql, "source_file": os.path.basename(path)}


def priorities_filtered_out(jql):
    """Which of P1..P5 a `priority <op> N` clause in the JQL removes.

    Jira compares priorities by their position in the scheme; in the exports
    this skill was built against the priority *names* are the numerals 1-5 and
    the comparison behaves numerically on that name (`priority >= 2` returns
    2,3,4,5). Treat the result as a caveat to show the reader, not as fact --
    it exists so a filtered zero is never read as a real zero.
    """
    if not jql:
        return []
    m = re.search(r"priority\s*(>=|<=|>|<|=)\s*(\d)", jql, flags=re.I)
    if not m:
        return []
    op, n = m.group(1), int(m.group(2))
    keep = {">=": lambda p: p >= n, "<=": lambda p: p <= n, ">": lambda p: p > n,
            "<": lambda p: p < n, "=": lambda p: p == n}[op]
    return [str(p) for p in range(1, 6) if not keep(p)]


# ------------------------------------------------------------------- html ---
def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def heat_shade(n):
    if n == 0:  return HEAT_SHADES[0]
    if n <= 2:  return HEAT_SHADES[1]
    if n <= 5:  return HEAT_SHADES[2]
    if n <= 9:  return HEAT_SHADES[3]
    return HEAT_SHADES[4]


def build(issues, meta, cfg):
    phase_of = dict(DEFAULT_PHASE_OF); phase_of.update(cfg["phase_of"])
    status_order = cfg["status_order"] or DEFAULT_STATUS_ORDER
    # any configured status the default order doesn't know about goes on the end
    status_order = status_order + [s for s in phase_of if s not in status_order]

    seen = {i["status"] for i in issues}
    unmapped = sorted(s for s in seen if s not in phase_of)
    if unmapped:
        raise SystemExit(
            "ERROR: these statuses are not mapped to a lifecycle phase:\n  "
            + "\n  ".join(unmapped)
            + "\n\nAdd each one to \"phase_of\" in the config file, mapping it to one of:\n  "
            + ", ".join(PHASES + [DEFERRED])
            + "\nDo not guess -- an unmapped status silently landing in the wrong\n"
              "column is the one failure this page cannot show on its face.\n"
              "See references/lifecycle-mapping.md.")

    as_of = cfg["as_of"] or meta["generated_at"] or dt.datetime.now(dt.timezone.utc)
    if isinstance(as_of, str):
        as_of = dt.datetime.fromisoformat(as_of.replace("Z", "+00:00"))

    def age(i, field="created"):
        return (as_of - email.utils.parsedate_to_datetime(i[field])).days

    TOTAL = len(issues)
    if TOTAL == 0:
        raise SystemExit("ERROR: the export contains no issues -- nothing to render.")

    ph = lambda i: phase_of[i["status"]]
    by_status = collections.Counter(i["status"] for i in issues)
    by_phase = collections.Counter(ph(i) for i in issues)
    prio_in_phase = collections.Counter((ph(i), str(i["priority"])) for i in issues)

    # Priority totals exclude the configured phases -- by default Customer
    # Testing, whose items are built and awaiting verification, so they are no
    # longer priority-weighted work to deliver. The page states this basis.
    excl = set(cfg["priority_exclude_phases"])
    prio_scope = [i for i in issues if ph(i) not in excl]
    by_prio = collections.Counter(str(i["priority"]) for i in prio_scope)
    PRIO_BASE, PRIO_EXCL_N = len(prio_scope), TOTAL - len(prio_scope)

    backlog_n = by_phase[PHASES[0]]
    backlog_pct = round(100 * backlog_n / TOTAL)
    in_flight = TOTAL - backlog_n - by_phase[DEFERRED]
    backlog_ages = sorted(age(i) for i in issues if ph(i) == PHASES[0])
    backlog_median = backlog_ages[len(backlog_ages) // 2] if backlog_ages else 0

    # -- 30-day creation heatmap ------------------------------------------
    HD = cfg["heat_days"]
    today = as_of.date()
    heat_start = today - dt.timedelta(days=HD - 1)
    created_on = collections.Counter(
        email.utils.parsedate_to_datetime(i["created"]).astimezone(dt.timezone.utc).date()
        for i in issues)
    heat_total = sum(created_on[heat_start + dt.timedelta(days=d)] for d in range(HD))

    # Rows are weeks, columns Mon-Sun: a transposed GitHub grid, which fits a
    # wide landscape panel where the tall original would not.
    grid_start = heat_start - dt.timedelta(days=heat_start.weekday())
    n_weeks = ((today - grid_start).days // 7) + 1
    heat_rows = []
    for w in range(n_weeks):
        wk = grid_start + dt.timedelta(days=7 * w)
        cells = []
        for d in range(7):
            day = wk + dt.timedelta(days=d)
            if day < heat_start or day > today:
                cells.append('<span class="cell out"></span>')
            else:
                n = created_on[day]
                cells.append(f'<span class="cell" style="background:{heat_shade(n)}" '
                             f'title="{day:%a %d %b}: {n}">{f"<b>{n}</b>" if n else ""}</span>')
        heat_rows.append(f'<div class="hrow"><span class="wlabel">{wk:%d %b}</span>'
                         + "".join(cells) + "</div>")
    dow_html = ('<div class="hrow head"><span class="wlabel">w/c</span>'
                + "".join(f'<span class="dow">{d}</span>' for d in "MTWTFSS") + "</div>")
    heat_legend = ('<span class="li">Fewer</span>'
                   + "".join(f'<span class="sw" style="background:{c}"></span>' for c in HEAT_SHADES)
                   + '<span class="li">More</span>')

    # -- KPI strip ---------------------------------------------------------
    filtered = priorities_filtered_out(meta["jql"])
    kpis = [
        f'<div class="kpi hero"><div class="k-label">Total open defects</div>'
        f'<div class="k-val">{TOTAL}</div>'
        f'<div class="k-sub">{in_flight} in flight &middot; {by_phase[DEFERRED]} deferred</div></div>',
        f'<div class="kpi hero alt"><div class="k-label">Still in backlog</div>'
        f'<div class="k-val">{backlog_pct}<span class="pct">%</span></div>'
        f'<div class="k-sub">{backlog_n} of {TOTAL} not yet started</div></div>',
    ]
    for p in PRIOS:
        n = by_prio.get(p, 0)
        thr = cfg["priority_thresholds"].get(p)
        hot = thr is not None and n > thr
        if p in filtered and n == 0:
            sub = "excluded by query"
        elif hot:
            sub = "&#9650; over threshold"
        else:
            sub = f"threshold &gt;{thr}" if thr is not None else "&nbsp;"
        kpis.append(
            f'<div class="kpi prio{" hot" if hot else ""}{" filtered" if p in filtered and n == 0 else ""}">'
            f'<div class="k-label"><span class="pdot" style="background:{PRIO_COLOR[p]}"></span>P{p}'
            f'<span class="kscope">to deliver</span></div>'
            f'<div class="k-val">{n}</div><div class="k-sub">{sub}</div></div>')

    # -- phase cards -------------------------------------------------------
    MAX_STATUS = max(by_status.values())
    cards = []
    for idx, phase in enumerate(PHASES):
        n = by_phase.get(phase, 0)
        counts = {p: prio_in_phase.get((phase, p), 0) for p in PRIOS}
        rows = "".join(
            f'<div class="srow"><span class="sname">{esc(s)}</span>'
            f'<span class="sbar"><i style="width:{100*by_status[s]/MAX_STATUS:.3f}%;'
            f'background:{PHASE_COLOR[phase]}"></i></span>'
            f'<span class="sn">{by_status[s]}</span></div>'
            for s in status_order if phase_of.get(s) == phase and by_status.get(s))
        empty = [SHORT_STATUS.get(s, s) for s in status_order
                 if phase_of.get(s) == phase and not by_status.get(s)]
        if empty:
            rows += ('<div class="srow none"><span class="sname">'
                     + esc(" / ".join(empty)) + '</span><span class="sbar"></span>'
                     '<span class="sn">0</span></div>')
        bar = ('<div class="pbar empty"></div>' if not n else
               '<div class="pbar">' + "".join(
                   f'<span class="seg" style="width:{100*counts[p]/n:.4f}%;'
                   f'background:{PRIO_COLOR[p]}"></span>' for p in PRIOS if counts[p]) + "</div>")
        foot = "".join(f'<span class="pf"><i style="background:{PRIO_COLOR[p]}"></i>'
                       f'P{p}<b>{counts[p]}</b></span>' for p in PRIOS if counts[p]) \
               or '<span class="pf none">no items</span>'
        chev = '<div class="chev">&rsaquo;</div>' if idx < len(PHASES) - 1 else ""
        cards.append(
            f'<div class="phase" style="--pc:{PHASE_COLOR[phase]}">'
            f'<div class="p-name">{idx+1}. {esc(phase)}</div>'
            f'<div class="p-blurb">{PHASE_BLURB.get(phase, "&nbsp;")}</div>'
            f'<div class="p-fig"><span class="p-n">{n}</span>'
            f'<span class="p-pct">{round(100*n/TOTAL)}% of open</span></div>'
            f'{bar}<div class="p-statuses">{rows}</div>'
            f'<div class="p-foot">{foot}</div></div>{chev}')

    # -- deferred panel ----------------------------------------------------
    deferred = sorted([i for i in issues if ph(i) == DEFERRED],
                      key=lambda i: (i["status"], -age(i)))
    def_counts = collections.Counter(i["status"] for i in deferred)
    def_chips = " &middot; ".join(f"{v} {esc(k)}" for k, v in sorted(def_counts.items()))
    if not deferred:
        def_rows = ('<div class="dnone">No items are parked outside the flow &mdash; '
                    'nothing is blocked on the client or awaiting re-occurrence.</div>')
    elif len(deferred) <= cfg["deferred_detail_max"]:
        def_rows = "".join(
            f'<div class="drow"><span class="dstat">{esc(i["status"])}</span>'
            f'<span class="dkey">{esc(i["key"])}</span>'
            f'<span class="dprio" style="color:{PRIO_COLOR.get(str(i["priority"]),"#6a7280")}">'
            f'P{esc(i["priority"])}</span>'
            f'<span class="dsum">{esc(i["summary"])}</span>'
            f'<span class="dage">{age(i)}d</span></div>' for i in deferred)
    else:
        # Too many to name without turning the panel into a ticket list, which
        # is what this page is explicitly not for -- aggregate instead. The
        # rows carry the per-status split, so drop it from the header too.
        def_chips = ""
        def_rows = ""
        for status, n in sorted(def_counts.items(), key=lambda kv: -kv[1]):
            grp = [i for i in deferred if i["status"] == status]
            pmix = collections.Counter(str(i["priority"]) for i in grp)
            oldest = max(age(i) for i in grp)
            def_rows += (
                f'<div class="drow"><span class="dstat">{esc(status)}</span>'
                f'<span class="dagg"><b>{n}</b> items</span>'
                f'<span class="dsum">'
                + " ".join(f'<span class="pf"><i style="background:{PRIO_COLOR[p]}"></i>'
                           f'P{p}<b>{pmix[p]}</b></span>' for p in PRIOS if pmix[p])
                + f'</span><span class="dage">oldest {oldest}d</span></div>')

    # -- footnote ----------------------------------------------------------
    if cfg["footnote"]:
        para = cfg["footnote"]
    else:
        para = (
            f'Of <b>{TOTAL}</b> open defects, <b>{in_flight}</b> are actively moving through the '
            f'lifecycle and <b>{by_phase[PHASES[-1]]}</b> have reached the customer environment. '
            f'The dominant signal is the <b>{backlog_pct}% still in backlog</b> &mdash; {backlog_n} '
            f'items raised but not yet started, median age {backlog_median} days &mdash; so '
            f'throughput, rather than intake, is the constraint to plan around. Intake remains live: '
            f'<b>{heat_total}</b> of the {TOTAL} were raised in the last {HD} days.')
    filt_note = ""
    if filtered:
        filt_note = (" The query excludes P" + ", P".join(filtered)
                     + ", so those tiles reflect the filter rather than the true position.")
    src = (f'Source: one Jira XML export ({esc(meta["source_file"])})'
           + (f' generated {meta["generated_at"]:%a %d %b %Y %H:%M} UTC' if meta["generated_at"] else "")
           + (f' &mdash; JQL <code>{esc(meta["jql"])}</code>.' if meta["jql"] else ".")
           + filt_note
           + " Counts are a point-in-time snapshot: a single export carries no status-change "
             "history, so no movement between phases is implied.")

    projects = sorted({i["project"] for i in issues})
    # Precedence: --title on the command line (usually a title the user gave in
    # the invoking prompt) > report_title in the config > a neutral default.
    # The project key is deliberately not folded in -- a title assembled from
    # the export reads like a machine label, and the reader nearly always has a
    # name for this report already.
    title = cfg["report_title"] or cfg["title"] or "Defect Pipeline"
    subtitle = cfg["subtitle"] or ("Open defects by position in the lifecycle &middot; "
                                   + ", ".join(projects))
    prio_legend = "".join(f'<span class="li"><i style="background:{PRIO_COLOR[p]}"></i>P{p}</span>'
                          for p in PRIOS)

    stats = {"total": TOTAL, "by_phase": dict(by_phase), "by_status": dict(by_status),
             "priority_totals_excluding": sorted(excl), "by_priority": dict(by_prio),
             "priority_base": PRIO_BASE, "backlog_pct": backlog_pct,
             "raised_last_%dd" % HD: heat_total, "as_of": as_of.isoformat(),
             "priorities_filtered_by_jql": filtered}

    return _page(locals()), stats


def _page(v):
    """Assemble the HTML. CSS is tuned to fit one A4-landscape page -- see
    references/one-page-fit.md before changing any size or padding here."""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{esc(v['title'])}</title>
<style>
  @page {{ size: A4 landscape; margin: 8mm; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin:0; padding:0; background:#f4f5f7; color:#1c1c1c;
    font-family:-apple-system,"Segoe UI",Calibri,Helvetica,Arial,sans-serif; }}
  .page {{ width:281mm; min-height:190mm; margin:3mm auto; background:#fff;
    padding:5mm 9mm 2mm 9mm; box-shadow:0 1px 4px rgba(0,0,0,.12); }}
  @media print {{ body {{ background:#fff; }}
    .page {{ margin:0; box-shadow:none; min-height:0; }} }}

  .masthead {{ display:flex; justify-content:space-between; align-items:flex-end;
    border-bottom:2.5px solid #1F3864; padding-bottom:3px; margin-bottom:6px; }}
  .eyebrow {{ font-size:10.2px; letter-spacing:1.2px; font-weight:700; color:#B08D57;
    text-transform:uppercase; margin-bottom:2px; }}
  .masthead h1 {{ font-size:23px; margin:0; color:#1F3864; font-weight:800; letter-spacing:-.2px; }}
  .masthead .sub {{ font-size:11.5px; color:#55606e; margin-top:2px; }}
  .asof {{ text-align:right; font-size:10.2px; color:#55606e; line-height:1.5; }}
  .asof b {{ color:#1c1c1c; }}

  .sect {{ font-size:10px; font-weight:700; letter-spacing:.9px; text-transform:uppercase;
    color:#1F3864; margin:6px 0 4px 0; display:flex; align-items:center; gap:7px; }}
  .sect:after {{ content:""; flex:1; height:1px; background:#dfe2e6; order:3; }}
  .keyline {{ display:flex; gap:8px; order:4; margin-left:8px; }}
  .sect .hint {{ font-weight:600; letter-spacing:0; text-transform:none;
    color:#8a919b; font-size:9.4px; }}

  .kpis {{ display:grid; grid-template-columns:1.35fr 1.35fr repeat(5,1fr); gap:6px; }}
  .kpi {{ border:1px solid #dfe2e6; border-radius:5px; padding:7px 10px 6px 10px;
    background:#fff; border-top:3px solid #c9ced5; }}
  .kpi.hero {{ background:#1F3864; border-color:#1F3864; border-top-color:#B08D57; }}
  .kpi.hero .k-label {{ color:#c7d2e6; }} .kpi.hero .k-val {{ color:#fff; }}
  .kpi.hero .k-sub {{ color:#9fb0cc; }}
  .kpi.hero.alt {{ background:#2a4b7c; border-color:#2a4b7c; }}
  .kpi.prio {{ border-top-color:#dfe2e6; }}
  .kpi.hot {{ border-top-color:#C8393A; background:#fdf5f5; border-color:#f0d3d3; }}
  .kpi.hot .k-val {{ color:#B02418; }}
  .kpi.hot .k-sub {{ color:#B02418; font-weight:700; }}
  .kpi.filtered {{ background:#fafbfc; }}
  .kpi.filtered .k-val {{ color:#b7bcc4; }}
  .k-label {{ font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:.55px;
    color:#6a7280; display:flex; align-items:center; gap:4px; }}
  .k-val {{ font-size:31px; font-weight:800; color:#1F3864; line-height:1.05;
    margin-top:1px; letter-spacing:-.5px; }}
  .k-val .pct {{ font-size:18px; font-weight:700; margin-left:1px; }}
  .k-sub {{ font-size:8.6px; color:#8a919b; margin-top:1px; }}
  .pdot {{ width:8px; height:8px; border-radius:2px; display:inline-block; }}
  .kscope {{ font-size:7.2px; font-weight:600; letter-spacing:.2px; color:#a7adb6;
    text-transform:none; }}
  .kpi.hot .kscope {{ color:#c08a8a; }}
  .kpinote {{ font-size:8.4px; color:#8a919b; margin:4px 0 0 0; display:flex;
    align-items:center; gap:5px; }}
  .kpinote b {{ color:#55606e; }}
  .kpinote i {{ color:#B08D57; font-weight:700; font-style:normal; }}

  .flow {{ display:flex; align-items:stretch; }}
  .phase {{ flex:1; border:1px solid #dfe2e6; border-top:3.5px solid var(--pc);
    border-radius:5px; padding:6px 10px; background:#fff; min-width:0;
    display:flex; flex-direction:column; }}
  .chev {{ display:flex; align-items:center; color:#c3c8d0; font-size:26px;
    font-weight:700; padding:0 5px; line-height:1; }}
  .p-name {{ font-size:12.5px; font-weight:800; color:#1F3864; letter-spacing:-.1px; }}
  .p-blurb {{ font-size:9px; color:#8a919b; }}
  .p-fig {{ display:flex; align-items:baseline; gap:7px; margin:4px 0 5px 0; }}
  .p-n {{ font-size:33px; font-weight:800; color:var(--pc); line-height:1; letter-spacing:-.8px; }}
  .p-pct {{ font-size:9.4px; color:#6a7280; font-weight:600; }}
  .pbar {{ height:9px; border-radius:2px; overflow:hidden; display:flex; background:#eef0f2; }}
  .pbar.empty {{ background:repeating-linear-gradient(135deg,#fbfbfc,#fbfbfc 4px,#f2f3f5 4px,#f2f3f5 8px); }}
  .pbar .seg {{ height:100%; }}
  .p-statuses {{ margin-top:6px; border-top:1px solid #eef0f2; padding-top:2px; }}
  .srow {{ display:flex; align-items:center; gap:6px; font-size:9.6px; color:#3a3f47;
    padding:1.5px 0; border-bottom:1px dotted #f0f2f4; }}
  .srow:last-child {{ border-bottom:none; }}
  .srow .sname {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    padding-right:6px; width:106px; flex-shrink:0; }}
  .srow .sbar {{ flex:1; height:7px; background:#eef0f2; border-radius:2px;
    overflow:hidden; display:block; min-width:12px; }}
  .srow .sbar i {{ display:block; height:100%; }}
  .srow .sn {{ font-weight:800; color:#1F3864; font-size:10px; width:20px;
    text-align:right; flex-shrink:0; }}
  .srow.none {{ color:#b7bcc4; }} .srow.none .sn {{ color:#b7bcc4; font-weight:600; }}
  .srow.none .sbar {{ display:none; }}
  .srow.none .sname {{ width:auto; flex:1; font-style:italic; font-size:8.9px; }}
  .p-foot {{ margin-top:auto; padding-top:5px; display:flex; gap:9px; flex-wrap:wrap;
    border-top:1px solid #eef0f2; }}
  .pf {{ display:flex; align-items:center; gap:3px; font-size:9px; color:#6a7280; }}
  .pf i {{ width:8px; height:8px; border-radius:2px; display:inline-block; }}
  .pf b {{ color:#1F3864; font-size:9.6px; font-weight:800; }}
  .pf.none {{ color:#b7bcc4; }}

  .split {{ display:grid; grid-template-columns:1.32fr 1fr; gap:11px; align-items:stretch; }}
  .panel {{ border:1px solid #dfe2e6; border-radius:5px; padding:7px 10px 8px 10px; background:#fff; }}
  .panel.def {{ border-color:#eccccc; border-left:3px solid #B23A3A; background:#fefafa;
    display:flex; flex-direction:column; }}
  .drows {{ flex:1; display:flex; flex-direction:column; justify-content:space-around; }}
  .phead {{ font-size:9.2px; font-weight:700; margin-bottom:3px; letter-spacing:.3px; }}
  .pnote {{ font-weight:600; letter-spacing:0; text-transform:none; color:#8a919b; font-size:8.4px; }}
  .drow {{ display:flex; align-items:center; gap:7px; padding:7px 0;
    border-bottom:1px dotted #f0e0e0; }}
  .drow:last-child {{ border-bottom:none; }}
  .dstat {{ font-size:8.1px; font-weight:700; color:#fff; background:#B23A3A;
    padding:1.6px 5px; border-radius:3px; white-space:nowrap; letter-spacing:.2px;
    width:120px; text-align:center; flex-shrink:0; }}
  .dkey {{ font-size:9.4px; font-weight:800; color:#1F3864; width:82px; flex-shrink:0; }}
  .dagg {{ font-size:9.4px; color:#6a7280; width:60px; flex-shrink:0; }}
  .dagg b {{ color:#1F3864; font-weight:800; }}
  .dprio {{ font-size:9.4px; font-weight:800; width:19px; flex-shrink:0; }}
  .dsum {{ font-size:9.3px; color:#3a3f47; flex:1; overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap; display:flex; gap:9px; }}
  .dage {{ font-size:8.9px; color:#8a919b; font-weight:700; text-align:right;
    flex-shrink:0; white-space:nowrap; }}
  .dnone {{ font-size:9.4px; color:#8a3030; font-style:italic; padding:10px 0; }}

  .heat {{ margin-top:2px; }}
  .hrow {{ display:flex; gap:3px; margin-bottom:2px; align-items:center; }}
  .hrow.head {{ margin-bottom:2px; }}
  .wlabel {{ font-size:8.2px; color:#8a919b; width:36px; flex-shrink:0; text-align:right;
    padding-right:4px; font-weight:600; }}
  .hrow.head .wlabel {{ font-size:7.6px; text-transform:uppercase; letter-spacing:.4px; }}
  .dow {{ flex:1; text-align:center; font-size:7.6px; font-weight:700; color:#8a919b; }}
  .cell {{ flex:1; height:15.5px; border-radius:2.5px; display:flex; align-items:center;
    justify-content:center; font-size:9px; color:#fff; }}
  .cell b {{ font-weight:800; }}
  .cell[style*="#c7dcf2"] b, .cell[style*="#8ab4e0"] b {{ color:#1F3864; }}
  .cell.out {{ background:transparent; border:1px dashed #eceef1; }}
  .hfoot {{ display:flex; align-items:center; margin-top:5px; }}
  .legend {{ display:flex; gap:9px; flex-wrap:wrap; margin-top:3px; }}
  .li {{ display:flex; align-items:center; gap:4px; font-size:8.6px; color:#6a7280; }}
  .li i {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
  .heatleg {{ gap:3px; align-items:center; margin-top:0; flex-wrap:nowrap;
    white-space:nowrap; flex-shrink:0; }}
  .heatleg .sw {{ width:9.5px; height:9.5px; border-radius:2.5px; display:inline-block; }}
  .heatleg .li {{ font-size:7.4px; }}

  .footnote {{ margin-top:4px; padding-top:3px; border-top:1px solid #dfe2e6;
    display:flex; gap:9px; align-items:flex-start; }}
  .footnote .mark {{ font-size:17px; color:#B08D57; line-height:1; margin-top:1px; }}
  .footnote p {{ margin:0; font-size:9.6px; line-height:1.45; color:#454b54; font-style:italic; }}
  .footnote p b {{ color:#1F3864; font-style:normal; }}
  .footnote .src {{ font-style:normal; color:#8a919b; font-size:8.1px; margin-top:2px; line-height:1.4; }}
  .footnote code {{ font-family:Consolas,monospace; font-size:8.1px; color:#6a7280; }}
</style></head>
<body><div class="page">

  <div class="masthead">
    <div>
      <div class="eyebrow">{esc(v['cfg']['eyebrow'])}</div>
      <h1>{esc(v['title'])}</h1>
      <div class="sub">{v['subtitle']}</div>
    </div>
    <div class="asof">
      As at <b>{v['as_of']:%a %d %b %Y, %H:%M} UTC</b><br>
      Single Jira export &middot; <b>{v['TOTAL']}</b> open work items
    </div>
  </div>

  <div class="kpis">{"".join(v['kpis'])}</div>
  <div class="kpinote"><i>&#9656;</i>P1&ndash;P5 count the
    <b>{v['PRIO_BASE']} items still to be delivered</b>{
      f" &mdash; the {v['PRIO_EXCL_N']} in " + ", ".join(sorted(v['excl'])) +
      " are excluded, being built and awaiting customer verification"
      if v['PRIO_EXCL_N'] else ""}. Thresholds: {
      ", ".join(f"P{p}&nbsp;&gt;{t}" for p, t in sorted(v['cfg']['priority_thresholds'].items()))}.</div>

  <div class="sect">Where the work is sitting
    <span class="hint">bar beneath each count = priority mix within that phase</span>
    <span class="keyline">{v['prio_legend']}</span></div>
  <div class="flow">{"".join(v['cards'])}</div>

  <div class="sect">Deferred items &amp; intake</div>
  <div class="split">
    <div class="panel def">
      <div class="phead" style="color:#8a3030">DEFERRED &mdash; OUTSIDE THE FLOW, AWAITING A TRIGGER
        &nbsp;<span class="pnote">{v['by_phase'][DEFERRED]} items{
          ": " + v['def_chips'] if v['def_chips'] else ""}</span></div>
      <div class="drows">{v['def_rows']}</div>
    </div>
    <div class="panel">
      <div class="phead" style="color:#1F3864">DEFECTS RAISED &mdash; LAST {v['HD']} DAYS
        &nbsp;<span class="pnote">{v['heat_total']} of {v['TOTAL']} open items</span></div>
      <div class="heat">{v['dow_html']}{"".join(v['heat_rows'])}</div>
      <div class="hfoot"><div class="legend heatleg">{v['heat_legend']}</div></div>
    </div>
  </div>

  <div class="footnote">
    <div class="mark">&#9670;</div>
    <div><p>{v['para']}</p><div class="src">{v['src']}</div></div>
  </div>

</div></body></html>
"""


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print(__doc__); sys.exit(1)
    cfg = dict(DEFAULT_CONFIG)
    if "--config" in args:
        i = args.index("--config")
        cfg.update(json.load(open(args[i + 1])))
        del args[i:i + 2]
    if "--title" in args:
        i = args.index("--title")
        cfg["report_title"] = args[i + 1]
        del args[i:i + 2]
    stats_only = "--print-stats" in args
    if stats_only:
        args.remove("--print-stats")

    src = args[0]
    issues, meta = parse_export(src)
    page, stats = build(issues, meta, cfg)

    if stats_only:
        print(json.dumps(stats, indent=2)); return
    out = args[1]
    with open(out, "w") as f:
        f.write(page)
    print(f"Wrote {out}", file=sys.stderr)
    print(json.dumps(stats, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
