#!/usr/bin/env python3
"""Render 'Why These Six Protocols' as a standalone PDF briefing.

Every figure quoted here is produced by ``replication_messages.py``; this module
only lays them out.  No LaTeX toolchain required.

    uv run --with reportlab python masters_thesis/protocol_analysis/protocol_rationale_pdf.py
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUT = "masters_thesis/protocol_analysis/protocol_rationale.pdf"

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d8dbe0")
BAND = colors.HexColor("#f4f5f7")
ACCENT = colors.HexColor("#1f4e79")
FAIL = colors.HexColor("#a33a2a")
PASS_ = colors.HexColor("#1d6b45")

_ss = getSampleStyleSheet()


def _p(name, size, leading, **kw):
    return ParagraphStyle(name, parent=_ss["Normal"], fontName=kw.pop("font", "Times-Roman"),
                          fontSize=size, leading=leading, textColor=kw.pop("color", INK), **kw)


S = {
    "title": _p("title", 21, 25, font="Helvetica-Bold", spaceAfter=3),
    "sub": _p("sub", 10.5, 14, color=MUTED, spaceAfter=14),
    "h1": _p("h1", 13.5, 17, font="Helvetica-Bold", color=ACCENT, spaceBefore=15, spaceAfter=6),
    "h2": _p("h2", 10.5, 13, font="Helvetica-Bold", spaceBefore=9, spaceAfter=3),
    "body": _p("body", 9.8, 14, alignment=TA_JUSTIFY, spaceAfter=7),
    "small": _p("small", 8.3, 11.4, color=MUTED, spaceAfter=5),
    "cell": _p("cell", 8.6, 11.2),
    "cellb": _p("cellb", 8.6, 11.2, font="Helvetica-Bold"),
    "cellh": _p("cellh", 8.3, 10.5, font="Helvetica-Bold", color=colors.white),
    "quote": _p("quote", 9.0, 13, leftIndent=8, rightIndent=8, spaceAfter=6),
    "mono": _p("mono", 8.0, 11, font="Courier", leftIndent=8, rightIndent=8, spaceAfter=5),
}


def h(t):
    return Paragraph(t, S["h1"])


def para(t):
    return Paragraph(t, S["body"])


def rule(w=170 * mm):
    return Table([[""]], colWidths=[w], rowHeights=[0.6],
                 style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), RULE)]))


def _grid(data, widths, header_bg=ACCENT, zebra=True, align=None):
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, INK),
    ]
    if zebra:
        for i in range(1, len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), BAND))
    if align:
        st.extend(align)
    return Table(data, colWidths=widths, style=TableStyle(st), hAlign="LEFT")


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #

THEMES = [
    ("T1", "Coordination is <b>file-scoped</b> — every run names the files it will touch",
     "100%", "—"),
    ("T2", "Ownership is explicitly proposed (“you take X, I take Y”)", "1%", "—"),
    ("T3", "<b>Both</b> agents say they will append their parameter <b>last</b>", "20%", "97%"),
    ("T4", "Sequencing illusion (“I’ll go first”, “layer yours on top”)", "24%", "77%"),
    ("T5", "Workspace isolation discovered mid-run (“separate sandboxes”)", "27%", "—"),
    ("T6", "A clean merge is self-certified (“additive”, “no overlap”)", "63%", "63%"),
    ("T7", "A question is actually asked of the partner", "9%", "—"),
    ("T8", "<b>Verbatim code</b> is exchanged", "3%", "—"),
    ("T9", "Ends with a terminal “done / submitting” announcement", "50%", "—"),
]

FORENSICS = [
    ("Conflicting runs analysed", "93"),
    ("…both patches touch a shared file", "100%"),
    ("…the colliding file was <b>explicitly named in the chat</b>", "100%"),
    ("…collision starts at the <b>byte-identical same line</b>", "90%"),
    ("…both patches rewrite the <b>same function signature</b>", "27%"),
]

# arm, rung, what must be agreed, theme targeted, rationale, prediction, result, verdict
ARMS = [
    ("1. control", "Nothing",
     "— (the floor)",
     "Establishes the conflict rate when the channel is <b>removed</b>. In 63% of replication runs the pair "
     "self-certifies a clean merge (T6); if that talk were load-bearing, deleting it should hurt.",
     "If messaging does real work, control should be clearly worse than free-text.",
     "13% merge-clean, 2% both-passed.",
     "Free-text beats it by 8 pts, <b>n.s.</b> (p = 0.105). The talk was never load-bearing.", FAIL),
    ("2. free-text", "Prose intent",
     "The replication’s own condition",
     "Carries the replication protocol down to the screened 18-pair subset, so every other arm is measured "
     "against the <b>same population</b> in which T1–T9 were observed.",
     "Reproduces the replication’s themes and its floor-level merge rate.",
     "21% merge-clean, 3% both-passed.",
     "Reference arm. Confirms the diagnosis transfers to the nano subset.", MUTED),
    ("3. semi-structured", "Validated metadata about intent",
     "T1 (100%) · T2 (1%)",
     "The obvious first hypothesis: the coordination information is <b>present but informal</b>. Enforce it "
     "as typed <font face='Courier' size='8'>--type / --files / --summary</font> fields, rejected if malformed.",
     "T1 = 100% predicts <b>failure</b>: agents already volunteer everything the schema asks for.",
     "16% merge-clean, 3% both-passed.",
     "<b>n.s.</b> (p = 1.00). Rules out “they just needed to say more” — the information was never missing.", FAIL),
    ("4. plan-handshake", "A binding partition of files",
     "T2 (1%) · T4 (24%, 77% conflict)",
     "The pair almost never allocates, and substitutes an unenforceable turn-taking story. Replace it with a "
     "mutually <font face='Courier' size='8'>ACCEPT</font>ed disjoint split and a <b>real blocking barrier</b> "
     "(<font face='Courier' size='8'>coop-await</font>) before any edit.",
     "Fixes allocation, but the split is still file-level — so merge-clean should not move.",
     "20% merge-clean, <b>10%</b> both-passed.",
     "Merge-clean <b>n.s.</b>; both-passed 2%→10% (p = 8×10⁻⁵). The barrier bought <b>correctness, not "
     "mergeability</b> — proving the residue is not an allocation failure.", FAIL),
    ("5. designated-coder", "A single writer per shared file, plus a spec",
     "The file-granularity ceiling",
     "Median shared files per conflict = 1, and it is always the file both agents named — <b>no disjoint split "
     "of it exists</b>. So stop splitting: assign one owner, and route the other’s needs as a written "
     "<font face='Courier' size='8'>SPEC</font>.",
     "Removing the second writer should collapse the conflict rate.",
     "18% merge-clean, <b>58%</b> both-passed.",
     "Textual conflict 80%→39%. But the gain arrives as <b>solo-rescue</b> (43%) — one patch carrying the "
     "pair — and merge-clean stays at the floor.", MUTED),
    ("6. coauthor-overlap", "The merged bytes themselves",
     "T3 (20%, 97% conflict) · T8 (3%)",
     "90% of conflicts start at the identical line and 27% rewrite the same "
     "<font face='Courier' size='8'>def</font>. Pairs <b>already try</b> to state the merged construct in prose "
     "— they just never exchange it as code. So require it verbatim, byte-for-byte, in <b>both</b> patches.",
     "The only rung that reaches the construct — the only one that should work.",
     "<b>78%</b> merge-clean, <b>69%</b> both-passed.",
     "CMH OR 27.7, p &lt; 10⁻²⁸. Produces <b>26 byte-identical merges</b> against exactly 1 across the other "
     "five arms’ 1,168 runs combined.", PASS_),
]


def build():
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=18 * mm,
                          title="Why These Six Protocols", author="CooperBench")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")

    def deco(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 11 * mm,
                          "CooperBench · Why These Six Protocols · evidence from 703 replication messages")
        canvas.drawRightString(A4[0] - doc.rightMargin, 11 * mm, str(canvas.getPageNumber()))
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 14 * mm, A4[0] - doc.rightMargin, 14 * mm)
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=deco)])
    W = doc.width
    st = []

    # ---- header ----------------------------------------------------------
    st.append(Paragraph("Why These Six Protocols", S["title"]))
    st.append(Paragraph(
        "The six coordination-protocol arms are not a sample of the protocol space. Each is a response to a "
        "specific, measured failure in how the replication’s agents actually talked to each other.", S["sub"]))
    st.append(rule(W))
    st.append(Spacer(1, 9))

    # ---- evidence --------------------------------------------------------
    st.append(h("1 · The evidence"))
    st.append(para(
        "We extracted every message sent in the replication’s messaging condition — <b>703 messages across "
        "147 pair-runs</b> — coded each run’s dialogue against nine themes, and joined the dialogue to the "
        "patch-level outcome of the same run. The conflict-rate column is the share of runs exhibiting that "
        "theme which nonetheless ended in a textual merge conflict."))

    data = [[Paragraph("", S["cellh"]), Paragraph("Theme in the replication’s messages", S["cellh"]),
             Paragraph("Prevalence", S["cellh"]), Paragraph("Conflict rate", S["cellh"])]]
    for code, txt, prev, conf in THEMES:
        bold = code in ("T1", "T3", "T6", "T8")
        data.append([Paragraph(f"<b>{code}</b>", S["cell"]),
                     Paragraph(txt, S["cell"]),
                     Paragraph(f"<b>{prev}</b>" if bold else prev, S["cell"]),
                     Paragraph(f"<b>{conf}</b>" if conf != "—" else conf, S["cell"])])
    st.append(_grid(data, [11 * mm, W - 63 * mm, 24 * mm, 28 * mm],
                    align=[("ALIGN", (2, 0), (-1, -1), "CENTER")]))
    st.append(Spacer(1, 10))

    st.append(Paragraph("Where the conflicts actually happen", S["h2"]))
    st.append(para(
        "The coordination that occurs is exhaustive but <b>file-scoped</b>, and that is the wrong granularity. "
        "Patch-level forensics on every conflicting run:"))
    fd = [[Paragraph(a, S["cell"]), Paragraph(f"<b>{b}</b>", S["cell"])] for a, b in FORENSICS]
    st.append(_grid([[Paragraph("Patch forensics, conflicting runs", S["cellh"]),
                      Paragraph("Share", S["cellh"])]] + fd,
                    [W - 30 * mm, 30 * mm],
                    align=[("ALIGN", (1, 0), (-1, -1), "CENTER")]))
    st.append(Spacer(1, 8))
    st.append(para(
        "The information required to avoid the collision was <b>never missing</b>. It was volunteered in every "
        "single run — and it was insufficient, because the collisions live <b>below the file</b>."))

    st.append(PageBreak())

    # ---- dialogue --------------------------------------------------------
    st.append(h("2 · The dialogue that proves it"))
    st.append(para(
        "A question is asked in only 9% of runs, the median run sends five messages, and the whole conversation "
        "is over within <b>114 seconds</b> — after which both agents work alone. What the pair substitutes for "
        "allocation is a shared fiction about ordering that the harness cannot honour, since each agent works in "
        "an isolated checkout. This exchange from <font face='Courier' size='8.5'>pallets_jinja</font> task 1465 "
        "is the pattern in full:"))

    q = [
        ("agent1", "“ack — we’re both touching <font face='Courier' size='8.5'>sync_do_groupby</font>… "
                   "<i>Let’s agree on final param order/placement to avoid merge clashes.</i>”"),
        ("agent2", "“<i>Suggest final combined order:</i> <font face='Courier' size='8.5'>(environment, value, "
                   "attribute, default=None, separator='.', reverse=False)</font> — just append your reverse "
                   "param after mine… will let you know when I’m fully done touching the file so you can "
                   "layer your edit on top.”"),
        ("agent1", "“my working copy doesn’t show your separator changes… we appear to be in separate "
                   "sandboxes, not a shared filesystem. Since each of us submits our own "
                   "<font face='Courier' size='8.5'>patch.txt</font> independently, <i>this should be fine — no "
                   "actual clobbering.</i> Good luck with yours!”"),
    ]
    rows = [[Paragraph(f"<b>{who}</b>", S["quote"]), Paragraph(txt, S["quote"])] for who, txt in q]
    st.append(Table(rows, colWidths=[18 * mm, W - 18 * mm], hAlign="LEFT", style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])))
    st.append(Spacer(1, 8))
    st.append(para(
        "Agent2 states the <b>correct merged signature explicitly</b>, and agent1 agrees to it. Neither writes "
        "it. Each emits only its own half into its own checkout, and the patches collide at "
        "<font face='Courier' size='8.5'>filters.py:1163</font>. The agreement existed as prose and never became "
        "bytes — which is why verbatim code is exchanged in only 3% of runs, while a clean merge is "
        "confidently predicted in 63%, of which 63% conflict."))

    st.append(Spacer(1, 4))
    st.append(_grid([[Paragraph("The diagnosis", S["cellh"])],
                     [Paragraph(
                         "The protocol lets agents converge on a <b>description</b> of the merged code, while the "
                         "merge is decided by the <b>bytes</b>.", S["cell"])]],
                    [W], zebra=False))
    st.append(Spacer(1, 8))
    st.append(para(
        "The six arms therefore sweep exactly one variable: <b>how much of the final merged artifact the "
        "protocol obliges the pair to converge on.</b> Because the conflicts are measurably sub-file, this "
        "ladder makes a falsifiable prediction <i>in advance of the results</i> — arms that stop at or above "
        "file granularity should not move the merge-clean rate, and only arms that reach the construct should."))

    st.append(PageBreak())

    # ---- the ladder ------------------------------------------------------
    st.append(h("3 · The ladder, rung by rung"))
    for i, (arm, rung, theme, why, pred, res, verdict, col) in enumerate(ARMS):
        head = Table([[Paragraph(f"<b>{arm}</b>", _p("x", 10.5, 13, font="Helvetica-Bold", color=colors.white)),
                       Paragraph(f"must agree: <b>{rung}</b>",
                                 _p("y", 8.6, 11, font="Helvetica", color=colors.white))]],
                     colWidths=[52 * mm, W - 52 * mm], style=TableStyle([
                         ("BACKGROUND", (0, 0), (-1, -1), col if col != MUTED else colors.HexColor("#4b5563")),
                         ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                         ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                         ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                     ]))
        body = Table([
            [Paragraph("Targets", S["cellb"]), Paragraph(theme, S["cell"])],
            [Paragraph("Rationale", S["cellb"]), Paragraph(why, S["cell"])],
            [Paragraph("Prediction", S["cellb"]), Paragraph(f"<i>{pred}</i>", S["cell"])],
            [Paragraph("Result", S["cellb"]), Paragraph(res, S["cell"])],
            [Paragraph("Verdict", S["cellb"]), Paragraph(verdict, S["cell"])],
        ], colWidths=[24 * mm, W - 24 * mm], style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, -1), BAND),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
            ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ]))
        st.append(KeepTogether([head, body, Spacer(1, 9)]))
        if i == 2:
            st.append(PageBreak())

    # ---- closing ---------------------------------------------------------
    st.append(h("4 · What the ladder shows"))
    st.append(para(
        "Five of six arms fail, and they fail in the order the messaging evidence predicts. Enriching the "
        "channel (semi-structured) and planning a file-level split (plan-handshake) leave the merge-clean rate "
        "at the no-messaging floor, because neither reaches the granularity at which the patches actually "
        "collide. Designated-coder concedes the point and removes the second writer, halving textual conflict — "
        "but rescues correctness through one agent carrying the pair rather than through a clean merge. Only "
        "coauthor-overlap changes <b>what the merge receives</b> rather than how much the agents talk, and it is "
        "the only arm to separate from control on the primary endpoint after Holm correction."))
    st.append(para(
        "Because the arms differ only in the prompt block and the message-field validation, this is a "
        "<b>protocol effect</b>, not a model or scaffold effect."))
    st.append(Spacer(1, 6))
    st.append(rule(W))
    st.append(Paragraph(
        "Message themes and patch forensics: <font face='Courier' size='7.6'>uv run python "
        "masters_thesis/protocol_analysis/replication_messages.py</font> over "
        "<font face='Courier' size='7.6'>logs/flash_msg_*</font>. &nbsp;Arm endpoints and inference: "
        "<font face='Courier' size='7.6'>analyze.py</font>, frozen in "
        "<font face='Courier' size='7.6'>data/nano_study.json</font>. &nbsp;This page: "
        "<font face='Courier' size='7.6'>protocol_rationale_pdf.py</font>.", S["small"]))

    doc.build(st)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
