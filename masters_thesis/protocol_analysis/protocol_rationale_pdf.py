#!/usr/bin/env python3
"""Render 'Why These Six Protocols' as a slide-ready PDF in three sections.

Laid out as discrete blocks, each sized to become one PowerPoint slide and
labelled with its slide number, a headline, bullets, and a takeaway line.
Every figure quoted is produced by ``replication_messages.py``; this module
only lays them out.  No LaTeX toolchain required.

    uv run --with reportlab python masters_thesis/protocol_analysis/protocol_rationale_pdf.py
"""

from __future__ import annotations

import os

from reportlab.lib import colors
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
GREY = colors.HexColor("#4b5563")
WIN = colors.HexColor("#1d6b45")

_ss = getSampleStyleSheet()


def _p(name, size, leading, **kw):
    return ParagraphStyle(name, parent=_ss["Normal"], fontName=kw.pop("font", "Helvetica"),
                          fontSize=size, leading=leading, textColor=kw.pop("color", INK), **kw)


S = {
    "title": _p("title", 22, 26, font="Helvetica-Bold", spaceAfter=3),
    "sub": _p("sub", 10, 14, color=MUTED, spaceAfter=4),
    "slideno": _p("slideno", 7.6, 10, font="Helvetica-Bold", color=colors.white),
    "slidetitle": _p("slidetitle", 12, 15, font="Helvetica-Bold", color=colors.white),
    "bullet": _p("bullet", 9.4, 13.4, leftIndent=12, bulletIndent=2, spaceAfter=3.5),
    "take": _p("take", 9.2, 12.6, font="Helvetica-Oblique"),
    "takeb": _p("takeb", 8, 10, font="Helvetica-Bold", color=WIN),
    "cell": _p("cell", 8.5, 11, font="Times-Roman"),
    "cellb": _p("cellb", 8.5, 11, font="Helvetica-Bold"),
    "cellh": _p("cellh", 8.2, 10.4, font="Helvetica-Bold", color=colors.white),
    "quote": _p("quote", 8.9, 12.6, font="Times-Roman"),
    "small": _p("small", 7.6, 10.4, color=MUTED, spaceAfter=4),
    "secno": _p("secno", 26, 28, font="Helvetica-Bold", color=colors.white),
    "sectitle": _p("sectitle", 14, 17, font="Helvetica-Bold", color=colors.white),
    "seclead": _p("seclead", 9, 12, color=colors.HexColor("#c8d4e0")),
}

MONO = "<font face='Courier' size='8'>{}</font>"


def bullets(items, style="bullet"):
    return [Paragraph(t, S[style], bulletText="•") for t in items]


def takeaway(text, colour=WIN):
    """The one line to put in bold at the bottom of the slide."""
    return Table([[Paragraph("TAKEAWAY", S["takeb"]), Paragraph(text, S["take"])]],
                 colWidths=[20 * mm, None], hAlign="LEFT", style=TableStyle([
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4f0")),
                     ("LINEBEFORE", (0, 0), (0, -1), 2.5, colour),
                     ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                     ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                 ]))


def slide(num, title, body, width, colour=ACCENT):
    """One slide-sized block: numbered header bar + body flowables."""
    head = Table([[Paragraph(f"SLIDE {num}", S["slideno"]), Paragraph(title, S["slidetitle"])]],
                 colWidths=[19 * mm, width - 19 * mm], style=TableStyle([
                     ("BACKGROUND", (0, 0), (-1, -1), colour),
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                     ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                 ]))
    inner = Table([[b] for b in body], colWidths=[width], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]))
    return KeepTogether([head, inner, Spacer(1, 11)])


def section(num, title, lead, width):
    band = Table([[Paragraph(num, S["secno"]),
                   Table([[Paragraph(title, S["sectitle"])], [Paragraph(lead, S["seclead"])]],
                         colWidths=[width - 24 * mm], style=TableStyle([
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 1),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                         ]))]],
                 colWidths=[24 * mm, width - 24 * mm], style=TableStyle([
                     ("BACKGROUND", (0, 0), (-1, -1), INK),
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                     ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                 ]))
    return KeepTogether([band, Spacer(1, 10)])


def grid(data, widths, centre_from=1):
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, INK),
        ("ALIGN", (centre_from, 0), (-1, -1), "CENTER"),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            st.append(("BACKGROUND", (0, i), (-1, i), BAND))
    return Table(data, colWidths=widths, style=TableStyle(st), hAlign="LEFT")


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #

THEMES = [
    ("T1", "Coordination is <b>file-scoped</b> — every run names the files it will touch", "100%", "—"),
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

LADDER = [
    ("1", "control", "Nothing", "13% / 2%"),
    ("2", "free-text", "Prose intent", "21% / 3%"),
    ("3", "semi-structured", "Validated metadata about intent", "16% / 3%"),
    ("4", "plan-handshake", "A binding partition of files", "20% / 10%"),
    ("5", "designated-coder", "A single writer per shared file", "18% / 58%"),
    ("6", "coauthor-overlap", "<b>The merged bytes themselves</b>", "<b>78% / 69%</b>"),
]

# num, arm, rung, targets, why (bullets), result, verdict, colour
ARMS = [
    ("3.1", "control — no messaging", "Must agree: nothing", "The floor", FAIL,
     ["Establishes the conflict rate when the channel is <b>removed entirely</b>.",
      "In 63% of replication runs the pair self-certifies a clean merge (T6). If that talk "
      "were load-bearing, deleting it should visibly hurt.",
      "<i>Prediction:</i> if messaging does real work, control should be clearly worse."],
     "13% merge-clean · 2% both-passed",
     "Free-text beats it by 8 points — <b>not significant</b> (p = 0.105). The talk was never load-bearing."),
    ("3.2", "free-text — unconstrained messaging", "Must agree: prose intent",
     "The replication’s own condition", GREY,
     ["Carries the replication protocol down to the screened 18-pair subset.",
      "Guarantees every other arm is measured against the <b>same population</b> in which "
      "themes T1–T9 were observed.",
      "<i>Prediction:</i> reproduces the replication’s themes and its floor-level merge rate."],
     "21% merge-clean · 3% both-passed",
     "Reference arm. Confirms the diagnosis transfers to the nano subset."),
    ("3.3", "semi-structured — typed, validated fields", "Must agree: metadata about intent",
     "Targets T1 (100%) · T2 (1%)", FAIL,
     ["Tests the obvious first hypothesis: the coordination information is <b>present but informal</b>.",
      "Enforces it as typed " + MONO.format("--type / --files / --summary") +
      " fields; malformed messages are rejected and never delivered.",
      "<i>Prediction:</i> T1 = 100% predicts <b>failure</b> — agents already volunteer everything "
      "the schema asks for."],
     "16% merge-clean · 3% both-passed",
     "<b>Not significant</b> (p = 1.00). Rules out “they just needed to say more” — the information "
     "was never missing."),
    ("3.4", "plan-handshake — agree a disjoint file split", "Must agree: a binding partition of files",
     "Targets T2 (1%) · T4 (24%, 77% conflict)", FAIL,
     ["The pair almost never allocates, and substitutes an <b>unenforceable turn-taking story</b>.",
      "Replaces it with a mutually " + MONO.format("ACCEPT") + "ed disjoint split and a "
      "<b>real blocking barrier</b> (" + MONO.format("coop-await") + ") before any edit.",
      "<i>Prediction:</i> fixes allocation — but the split is still file-level, so merge-clean "
      "should not move."],
     "20% merge-clean · <b>10%</b> both-passed",
     "Merge-clean <b>n.s.</b>; both-passed 2%→10% (p = 8×10⁻⁵). The barrier bought <b>correctness, "
     "not mergeability</b> — so the residue is not an allocation failure."),
    ("3.5", "designated-coder — one owner per shared file", "Must agree: a single writer, plus a spec",
     "Targets the file-granularity ceiling", GREY,
     ["Median shared files per conflict = 1, and it is always the file <b>both agents named</b> — "
      "so no disjoint split of it exists.",
      "Stops splitting: assigns one owner, and routes the other’s needs as a written " +
      MONO.format("SPEC") + " instead of as conflicting edits.",
      "<i>Prediction:</i> removing the second writer should collapse the conflict rate."],
     "18% merge-clean · <b>58%</b> both-passed",
     "Textual conflict 80%→39%. But the gain arrives as <b>solo-rescue</b> (43%) — one patch carrying "
     "the pair — and merge-clean stays at the floor."),
    ("3.6", "coauthor-overlap — byte-identical merged code", "Must agree: the merged bytes themselves",
     "Targets T3 (20%, 97% conflict) · T8 (3%)", WIN,
     ["90% of conflicts start at the <b>identical line</b>; 27% rewrite the same " +
      MONO.format("def") + ".",
      "Pairs <b>already try</b> to state the merged construct in prose — they just never exchange "
      "it as code (T8 = 3%).",
      "So it requires that construct to be agreed and then emitted <b>verbatim, byte-for-byte, "
      "in both patches</b>.",
      "<i>Prediction:</i> the only rung reaching the construct — the only one that should work."],
     "<b>78%</b> merge-clean · <b>69%</b> both-passed",
     "CMH OR 27.7, p &lt; 10⁻²⁸. Produces <b>26 byte-identical merges</b> against exactly 1 across "
     "the other five arms’ 1,168 runs combined."),
]


def build():
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=16 * mm, bottomMargin=17 * mm,
                          title="Why These Six Protocols", author="CooperBench")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")

    def deco(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.3)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 10 * mm,
                          "CooperBench · Why These Six Protocols · slide pack")
        canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, str(canvas.getPageNumber()))
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 13 * mm, A4[0] - doc.rightMargin, 13 * mm)
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=deco)])
    W = doc.width
    st = []

    # ---- cover ------------------------------------------------------------
    st.append(Paragraph("Why These Six Protocols", S["title"]))
    st.append(Paragraph(
        "The six coordination-protocol arms are not a sample of the protocol space. Each answers a "
        "specific, measured failure in how the replication’s agents actually talked to each other.",
        S["sub"]))
    st.append(Spacer(1, 6))
    toc = [
        ("1", "The Problem", "What 703 replication messages reveal", "3 slides"),
        ("2", "The Design", "One axis, six rungs — and a prediction", "2 slides"),
        ("3", "The Six Arms", "Why each was chosen, and what happened", "7 slides"),
    ]
    st.append(grid(
        [[Paragraph("§", S["cellh"]), Paragraph("Section", S["cellh"]),
          Paragraph("Covers", S["cellh"]), Paragraph("Length", S["cellh"])]] +
        [[Paragraph(f"<b>{a}</b>", S["cell"]), Paragraph(f"<b>{b}</b>", S["cell"]),
          Paragraph(c, S["cell"]), Paragraph(d, S["cell"])] for a, b, c, d in toc],
        [10 * mm, 34 * mm, W - 76 * mm, 22 * mm], centre_from=3))
    st.append(Spacer(1, 14))

    # ======================= SECTION 1 =====================================
    st.append(section("1", "The Problem", "What 703 replication messages reveal", W))

    st.append(slide("1.1", "The agents coordinate — exhaustively, and at the wrong grain", [
        Spacer(1, 5),
        *bullets([
            "We extracted <b>every message</b> sent in the replication’s messaging condition: "
            "<b>703 messages across 147 pair-runs</b>.",
            "Each run’s dialogue was coded against nine themes, then joined to the "
            "<b>patch-level outcome</b> of the same run.",
            "The exchange is a pair of announcements, not a negotiation: a question is asked in "
            "<b>9%</b> of runs, the median run sends <b>5 messages</b>, and the whole conversation "
            "is over in <b>114 seconds</b> — after which both agents work alone.",
        ]),
        Spacer(1, 4),
        takeaway("They talk. They just don’t negotiate — and they stop talking almost immediately.", ACCENT),
    ], W))

    st.append(slide("1.2", "Nine themes in the replication’s messages", [
        Spacer(1, 5),
        grid([[Paragraph("", S["cellh"]), Paragraph("Theme", S["cellh"]),
               Paragraph("Prevalence", S["cellh"]), Paragraph("Conflict rate", S["cellh"])]] +
             [[Paragraph(f"<b>{c}</b>", S["cell"]), Paragraph(t, S["cell"]),
               Paragraph(f"<b>{p}</b>" if c in ("T1", "T3", "T6", "T8") else p, S["cell"]),
               Paragraph(f"<b>{x}</b>" if x != "—" else x, S["cell"])]
              for c, t, p, x in THEMES],
             [10 * mm, W - 78 * mm, 24 * mm, 28 * mm]),
        Paragraph("Prevalence = share of the 147 messaged pair-runs. Conflict rate = share of those runs "
                  "that nonetheless ended in a textual merge conflict.", S["small"]),
        takeaway("Files are named in every run (T1) — but almost nobody allocates them (T2), "
                 "and almost nobody sends code (T8).", ACCENT),
    ], W))

    st.append(PageBreak())

    st.append(slide("1.3", "Where the conflicts actually happen", [
        Spacer(1, 5),
        grid([[Paragraph("Patch forensics, conflicting runs", S["cellh"]),
               Paragraph("Share", S["cellh"])]] +
             [[Paragraph(a, S["cell"]), Paragraph(f"<b>{b}</b>", S["cell"])] for a, b in FORENSICS],
             [W - 46 * mm, 30 * mm]),
        Spacer(1, 4),
        *bullets([
            "Every collision happened inside a file the agents had <b>already discussed</b>.",
            "The information needed to avoid it was <b>never missing</b> — it was volunteered in "
            "every single run, and it was insufficient.",
        ]),
        Spacer(1, 3),
        takeaway("The conflicts live <b>below the file</b>. File-level coordination cannot reach them.", FAIL),
    ], W))

    st.append(slide("1.4", "The dialogue that proves it — pallets_jinja #1465", [
        Spacer(1, 5),
        Table([[Paragraph(f"<b>{w}</b>", S["quote"]), Paragraph(t, S["quote"])] for w, t in [
            ("agent1", "“ack — we’re both touching " + MONO.format("sync_do_groupby") +
                       "… <i>Let’s agree on final param order/placement to avoid merge clashes.</i>”"),
            ("agent2", "“<i>Suggest final combined order:</i> " +
                       MONO.format("(environment, value, attribute, default=None, separator='.', reverse=False)") +
                       " — just append your reverse param after mine… will let you know when I’m fully "
                       "done so you can layer your edit on top.”"),
            ("agent1", "“my working copy doesn’t show your separator changes… we appear to be in "
                       "<b>separate sandboxes</b>, not a shared filesystem. Since each of us submits our "
                       "own " + MONO.format("patch.txt") + " independently, <i>this should be fine — no "
                       "actual clobbering.</i> Good luck with yours!”"),
        ]], colWidths=[16 * mm, W - 34 * mm], hAlign="LEFT", style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BAND),
            ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ])),
        Spacer(1, 5),
        *bullets([
            "agent2 states the <b>correct merged signature explicitly</b>. agent1 agrees to it. "
            "<b>Neither writes it.</b>",
            "Each emits only its own half into its own checkout — the patches collide at " +
            MONO.format("filters.py:1163") + ".",
        ]),
        Spacer(1, 3),
        takeaway("The agreement existed as <b>prose</b> and never became <b>bytes</b>.", FAIL),
    ], W))

    st.append(PageBreak())

    # ======================= SECTION 2 =====================================
    st.append(section("2", "The Design", "One axis, six rungs — and a prediction", W))

    st.append(slide("2.1", "The diagnosis, and the variable it names", [
        Spacer(1, 5),
        Table([[Paragraph(
            "The protocol lets agents converge on a <b>description</b> of the merged code, "
            "while the merge is decided by the <b>bytes</b>.",
            _p("diag", 11, 15, font="Helvetica-Bold"))]],
            colWidths=[W - 16 * mm], hAlign="LEFT", style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf3f1")),
                ("LINEBEFORE", (0, 0), (0, -1), 3, FAIL),
                ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ])),
        Spacer(1, 6),
        *bullets([
            "So the six arms sweep exactly one variable: <b>how much of the final merged artifact "
            "the protocol obliges the pair to converge on</b>.",
            "Nothing else changes — same model, same tasks, same evaluation, same integration model. "
            "Only the protocol block in the prompt and the message-field validation.",
            "That makes any difference between arms a <b>protocol effect</b>, not a model or "
            "scaffold effect.",
        ]),
        Spacer(1, 3),
        takeaway("Six rungs on one ladder, not six unrelated ideas.", ACCENT),
    ], W))

    st.append(slide("2.2", "The ladder — and the prediction it makes in advance", [
        Spacer(1, 5),
        grid([[Paragraph("Rung", S["cellh"]), Paragraph("Protocol", S["cellh"]),
               Paragraph("What the pair must converge on", S["cellh"]),
               Paragraph("Merge-clean / both-passed", S["cellh"])]] +
             [[Paragraph(f"<b>{n}</b>", S["cell"]), Paragraph(f"<b>{a}</b>", S["cell"]),
               Paragraph(r, S["cell"]), Paragraph(res, S["cell"])] for n, a, r, res in LADDER],
             [12 * mm, 30 * mm, W - 94 * mm, 42 * mm], centre_from=3),
        Spacer(1, 5),
        *bullets([
            "Because the conflicts are measurably <b>sub-file</b> (slide 1.3), the ladder is "
            "falsifiable <i>before any arm is run</i>:",
            "→ arms stopping <b>at or above file granularity</b> should not move the merge-clean rate;",
            "→ only arms reaching <b>the construct</b> should.",
        ]),
        Spacer(1, 3),
        takeaway("Rungs 1–4 should fail, 5–6 should work. That is exactly what happens.", WIN),
    ], W))

    st.append(PageBreak())

    # ======================= SECTION 3 =====================================
    st.append(section("3", "The Six Arms", "Why each was chosen, and what happened", W))

    for i, (num, arm, rung, targets, colour, why, result, verdict) in enumerate(ARMS):
        body = [
            Spacer(1, 4),
            Table([[Paragraph(rung, S["cellb"]), Paragraph(targets, S["cell"])]],
                  colWidths=[62 * mm, W - 78 * mm], hAlign="LEFT", style=TableStyle([
                      ("BACKGROUND", (0, 0), (-1, -1), BAND),
                      ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                      ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                      ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                      ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                  ])),
            Spacer(1, 4),
            *bullets(why),
            Spacer(1, 3),
            Table([[Paragraph("RESULT", S["takeb"]), Paragraph(result, S["cellb"])]],
                  colWidths=[20 * mm, None], hAlign="LEFT", style=TableStyle([
                      ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                      ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                      ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                  ])),
            takeaway(verdict, colour),
        ]
        st.append(slide(num, arm, body, W, colour))
        if i in (1, 3):
            st.append(PageBreak())

    st.append(slide("3.7", "What the ladder shows", [
        Spacer(1, 5),
        *bullets([
            "<b>Five of six arms fail — in the order the messaging evidence predicts.</b>",
            "Enriching the channel (semi-structured) and planning a file-level split (plan-handshake) "
            "leave merge-clean at the <b>no-messaging floor</b>: neither reaches the granularity at "
            "which the patches actually collide.",
            "Designated-coder concedes the point and removes the second writer, halving textual "
            "conflict — but rescues correctness through <b>one agent carrying the pair</b>, not "
            "through a clean merge.",
            "Only coauthor-overlap changes <b>what the merge receives</b> rather than how much the "
            "agents talk. It is the only arm to separate from control on the primary endpoint after "
            "Holm correction.",
        ]),
        Spacer(1, 3),
        takeaway("Protocol design works — but only when it changes the bytes, not the conversation.", WIN),
    ], W))

    st.append(Spacer(1, 2))
    st.append(Paragraph(
        "Message themes and patch forensics: " + MONO.format(
            "uv run python masters_thesis/protocol_analysis/replication_messages.py") +
        " over " + MONO.format("logs/flash_msg_*") + ". &nbsp;Arm endpoints and inference: " +
        MONO.format("analyze.py") + ", frozen in " + MONO.format("data/nano_study.json") +
        ". &nbsp;This pack: " + MONO.format("protocol_rationale_pdf.py") + ".", S["small"]))

    doc.build(st)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
