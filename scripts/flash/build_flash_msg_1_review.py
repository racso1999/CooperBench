#!/usr/bin/env python3
"""Build a manual-review report for flash_msg_1: every pair with its full
inter-agent message transcript and evaluation results.

Reads:  results_csv/flash_msg_1.csv, logs/flash_msg_1/coop/.../{conversation,eval}.json,
        dataset/<repo>/task<id>/feature<n>/feature.md (titles)
Writes: reports/flash_msg_1_review.html  (self-contained, print-ready)

No statistics, no interpretation — raw evidence only, organised for reading.
"""

from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "results_csv" / "flash_msg_1.csv"
LOGS = ROOT / "logs"
DATASET = ROOT / "dataset"
OUT = ROOT / "reports" / "flash_msg_1_review.html"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def feature_title(repo: str, task_id: str, fid: str) -> str:
    md = DATASET / repo / f"task{task_id}" / f"feature{fid}" / "feature.md"
    if md.exists():
        m = re.search(r"\*\*Title\*\*:\s*(.+)", md.read_text(errors="ignore"))
        if m:
            return m.group(1).strip()
    return "(title unavailable)"


def load_rows() -> list[dict]:
    with open(CSV) as f:
        return list(csv.DictReader(f))


def categorise(r: dict) -> str:
    if r["error"]:
        return "not_evaluated"
    if r["both_passed"] == "True":
        return "pass"
    if r["a_indep_passed"] == "True" and r["b_indep_passed"] == "True":
        return "coordination_failure"
    return "capability_failure"


CAT_META = {
    "coordination_failure": ("1. Coordination failures", "Both agents passed their own feature independently, yet the pair failed.", "#b91c1c"),
    "pass": ("2. Passes", "Both features passed on the merged tree.", "#15803d"),
    "capability_failure": ("3. Capability failures", "At least one agent failed its own feature independently (includes unapplied patches).", "#b45309"),
    "not_evaluated": ("4. Not evaluated", "Evaluation never ran (error=no_eval); treat as missing data, not failure.", "#6b7280"),
}
CAT_ORDER = ["coordination_failure", "pass", "capability_failure", "not_evaluated"]


def indep_cell(r: dict, side: str) -> str:
    if r["error"]:
        return "&mdash; not evaluated"
    p, tp, tf = r[f"{side}_indep_passed"], r[f"{side}_indep_tests_passed"], r[f"{side}_indep_tests_failed"]
    reason = r[f"{side}_indep_reason"]
    badge = "PASS" if p == "True" else "FAIL"
    cls = "ok" if p == "True" else "bad"
    out = f'<span class="badge {cls}">{badge}</span> {esc(tp)} passed / {esc(tf)} failed'
    if reason:
        out += f' <span class="reason">({esc(reason)})</span>'
    return out


def merged_cell(r: dict, side: str) -> str:
    if r["error"]:
        return "&mdash; not evaluated"
    if r["merge_clean"] != "True":
        return '<span class="muted">&mdash; merge conflicted, tests not run</span>'
    p, tp, tf = r[f"{side}_merged_passed"], r[f"{side}_merged_tests_passed"], r[f"{side}_merged_tests_failed"]
    badge = "PASS" if p == "True" else "FAIL"
    cls = "ok" if p == "True" else "bad"
    return f'<span class="badge {cls}">{badge}</span> {esc(tp)} passed / {esc(tf)} failed'


def transcript_html(leaf: Path) -> str:
    conv_path = leaf / "conversation.json"
    if not conv_path.exists():
        return '<p class="muted">No conversation.json in this leaf.</p>'
    conv = json.loads(conv_path.read_text())
    if not conv:
        return '<p class="muted">No messages were exchanged.</p>'
    t0 = min(m["timestamp"] for m in conv)
    out = []
    for m in sorted(conv, key=lambda m: m["timestamp"]):
        dt = m["timestamp"] - t0
        off = f"+{int(dt // 60)}:{int(dt % 60):02d}"
        kind = f' <span class="kind">[{esc(m["kind"])}]</span>' if m.get("kind") else ""
        out.append(
            f'<div class="msg {esc(m["from"])}">'
            f'<div class="msghead"><b>{esc(m["from"])}</b> &rarr; {esc(m.get("to", "?"))}'
            f'{kind} <span class="toff">{off}</span></div>'
            f'<div class="msgbody">{esc(m["message"])}</div></div>'
        )
    return "\n".join(out)


def pair_section(r: dict, titles: dict) -> str:
    anchor = f"{r['repo']}-{r['task_id']}-{r['pair']}"
    leaf = LOGS / r["pair_dir"]
    fa, fb = r["feature_a"], r["feature_b"]
    ta = titles.get((r["repo"], r["task_id"], fa), "")
    tb = titles.get((r["repo"], r["task_id"], fb), "")
    outcome = r["outcome"] or ("no_eval" if r["error"] else "?")
    cat = categorise(r)
    colour = CAT_META[cat][2]
    n_msgs = r["messages_sent"] or "0"

    meta = (
        f"duration {float(r['duration_s']):.0f}s &middot; cost ${float(r['total_cost'] or 0):.2f} &middot; "
        f"{n_msgs} messages"
        if not r["error"]
        else "not evaluated"
    )

    return f"""
<section class="pair" id="{esc(anchor)}">
  <h2><span class="dot" style="background:{colour}"></span>{esc(r["repo"])} / task {esc(r["task_id"])} / {esc(r["pair"])}
      <span class="outcome" style="color:{colour}">{esc(outcome)}</span></h2>
  <p class="features">
    <b>Feature {esc(fa)} (agent 1):</b> {esc(ta)}<br>
    <b>Feature {esc(fb)} (agent 2):</b> {esc(tb)}
  </p>
  <p class="meta">{meta}</p>
  <table class="eval">
    <tr><th></th><th>Apply</th><th>Pre-merge (independent)</th><th>Post-merge</th></tr>
    <tr><td><b>Feature {esc(fa)}</b></td><td>{esc(r["apply_a"] or "—")}</td>
        <td>{indep_cell(r, "a")}</td><td>{merged_cell(r, "a")}</td></tr>
    <tr><td><b>Feature {esc(fb)}</b></td><td>{esc(r["apply_b"] or "—")}</td>
        <td>{indep_cell(r, "b")}</td><td>{merged_cell(r, "b")}</td></tr>
  </table>
  <p class="mergestat"><b>Merge:</b> {esc(r["merge_status"] or "—")}
     &middot; <b>both_passed:</b> {esc(r["both_passed"] or "—")}</p>
  <h3>Message transcript</h3>
  {transcript_html(leaf)}
  <p class="prov">Raw artifacts: <code>logs/{esc(r["pair_dir"])}/</code></p>
</section>"""


def build() -> None:
    rows = load_rows()
    rows.sort(key=lambda r: (CAT_ORDER.index(categorise(r)), r["repo"], int(r["task_id"] or 0), r["pair"]))

    titles: dict = {}
    for r in rows:
        for f in (r["feature_a"], r["feature_b"]):
            key = (r["repo"], r["task_id"], f)
            if key not in titles:
                titles[key] = feature_title(r["repo"], r["task_id"], f)

    # index table
    idx_rows = []
    for r in rows:
        cat = categorise(r)
        anchor = f"{r['repo']}-{r['task_id']}-{r['pair']}"
        idx_rows.append(
            f'<tr><td><a href="#{esc(anchor)}">{esc(r["repo"])}/{esc(r["task_id"])}/{esc(r["pair"])}</a></td>'
            f'<td style="color:{CAT_META[cat][2]}">{esc(r["outcome"] or "no_eval")}</td>'
            f"<td>{esc(r['merge_status'] or '—')}</td>"
            f"<td>{'✓' if r['a_indep_passed'] == 'True' else '✗' if not r['error'] else '—'}</td>"
            f"<td>{'✓' if r['b_indep_passed'] == 'True' else '✗' if not r['error'] else '—'}</td>"
            f"<td>{esc(r['messages_sent'] or '0')}</td></tr>"
        )

    sections = []
    cur_cat = None
    for r in rows:
        cat = categorise(r)
        if cat != cur_cat:
            title, desc, colour = CAT_META[cat]
            n = sum(1 for x in rows if categorise(x) == cat)
            sections.append(
                f'<div class="catdiv" style="border-color:{colour}"><h1 style="color:{colour}">{title} '
                f"({n} pairs)</h1><p>{desc}</p></div>"
            )
            cur_cat = cat
        sections.append(pair_section(r, titles))

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>flash_msg_1 — manual review report</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 52rem; margin: 2rem auto;
         padding: 0 1rem; color: #111; line-height: 1.45; }}
  h1 {{ font-size: 1.4rem; }}  h2 {{ font-size: 1.1rem; margin-bottom: .2rem; }}
  h3 {{ font-size: .95rem; margin: .8rem 0 .3rem; }}
  .pair {{ border-top: 1px solid #ccc; margin-top: 1.5rem; padding-top: .8rem; }}
  .dot {{ display: inline-block; width: .65em; height: .65em; border-radius: 50%; margin-right: .4em; }}
  .outcome {{ float: right; font-size: .85rem; font-family: monospace; }}
  .features, .meta, .mergestat {{ font-size: .85rem; margin: .25rem 0; }}
  .meta {{ color: #555; }}
  table.eval {{ border-collapse: collapse; font-size: .82rem; margin: .4rem 0; width: 100%; }}
  table.eval th, table.eval td {{ border: 1px solid #bbb; padding: .25rem .5rem; text-align: left; }}
  table.idx {{ border-collapse: collapse; font-size: .8rem; width: 100%; }}
  table.idx th, table.idx td {{ border: 1px solid #ccc; padding: .2rem .45rem; }}
  .badge {{ font-family: monospace; font-size: .75rem; font-weight: bold; padding: 0 .3em; }}
  .badge.ok {{ color: #15803d; }} .badge.bad {{ color: #b91c1c; }}
  .reason {{ color: #92400e; }}
  .muted {{ color: #777; }}
  .msg {{ border-left: 3px solid #94a3b8; margin: .5rem 0; padding: .3rem .6rem; background: #f8fafc; }}
  .msg.agent2 {{ border-left-color: #7c3aed; }}
  .msghead {{ font-size: .78rem; color: #444; }}
  .toff {{ float: right; font-family: monospace; color: #888; }}
  .kind {{ font-family: monospace; color: #7c3aed; }}
  .msgbody {{ white-space: pre-wrap; font-size: .85rem; margin-top: .15rem; }}
  .prov {{ font-size: .75rem; color: #666; }}
  .catdiv {{ border-top: 4px solid; margin-top: 2.5rem; padding-top: .5rem; }}
  @media print {{
    body {{ margin: 0; max-width: none; }}
    .pair {{ break-inside: avoid-page; page-break-inside: avoid; }}
    .catdiv {{ break-before: page; }}
    a {{ color: inherit; text-decoration: none; }}
  }}
</style></head><body>
<h1>flash_msg_1 — manual failure review</h1>
<p style="font-size:.85rem">Run: <code>flash_msg_1</code> (claude-sonnet-5, coop, free messaging) &middot;
50 pairs &middot; generated {generated} from <code>results_csv/flash_msg_1.csv</code> +
<code>logs/flash_msg_1/</code>. Post-merge tests only run when the merge was clean; conflicted
pairs show &ldquo;tests not run&rdquo;.</p>
<h1>Index</h1>
<table class="idx">
<tr><th>pair</th><th>outcome</th><th>merge</th><th>A indep</th><th>B indep</th><th>msgs</th></tr>
{"".join(idx_rows)}
</table>
{"".join(sections)}
</body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc)
    print(f"wrote {OUT} ({len(rows)} pairs, {OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
