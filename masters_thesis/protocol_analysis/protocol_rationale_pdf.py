#!/usr/bin/env python3
"""Render the protocol study as a three-page slide pack, one page per slide.

    1. Semantic patterns  — how the agents' messages were read and coded
    2. The protocols      — the six arms and what each one aims to fix
    3. The findings       — the two figures, and what they show

Written to be followable by someone who has never seen the benchmark: the setup
is stated before any result, and every term is defined at the point it is first
used (see SETUP on slide 1 and the JARGON box on slide 3).

PROVENANCE RULE. Every number on these pages is emitted by one of two scripts,
and each is labelled on the slide with which one:

  replication_messages.py  -- message counts, timings, mechanically-detectable
                              message features, and the patch-level forensics
                              (which file and which lines the two patches
                              actually collided on)
  analyze.py               -- per-arm endpoints, merge-status split, failure
                              taxonomy and the CMH tests, frozen in
                              data/nano_study.json

The pack presents two kinds of figure and labels each: literal counts over the
message text (does a filename token appear, does a question mark appear, does a
code block appear, how many messages, how long the exchange) and direct
comparisons of the two agents' diffs. Both are settled mechanically, so every
number reproduces by rerunning the script.

The phrase-list theme prevalences that earlier drafts carried (ownership talk,
"append mine last", sequencing talk, self-certified clean merges) and the
conflict rates conditional on them are computed by replication_messages.py but
are deliberately not presented here: they depend on the author's choice of
phrases and are lower bounds by construction, so they belong to a coding study
with its own reliability check. The argument stands on the diff forensics.

This module only lays those numbers out. No LaTeX toolchain required.

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
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "protocol_rationale.pdf")
FIGS = os.path.join(HERE, "figures")

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d8dbe0")
BAND = colors.HexColor("#f4f5f7")
ACCENT = colors.HexColor("#1f4e79")
FAIL = colors.HexColor("#a33a2a")
WIN = colors.HexColor("#1d6b45")

_ss = getSampleStyleSheet()


def _p(name, size, leading, **kw):
    return ParagraphStyle(name, parent=_ss["Normal"], fontName=kw.pop("font", "Helvetica"),
                          fontSize=size, leading=leading, textColor=kw.pop("color", INK), **kw)


S = {
    "slideno": _p("slideno", 8.5, 11, font="Helvetica-Bold", color=colors.white),
    "slidetitle": _p("slidetitle", 15, 18, font="Helvetica-Bold", color=colors.white),
    "slidesub": _p("slidesub", 8.6, 11, color=colors.HexColor("#c3d2e0")),
    "h2": _p("h2", 9.5, 12, font="Helvetica-Bold", color=ACCENT, spaceBefore=2, spaceAfter=3),
    "bullet": _p("bullet", 8.6, 12, leftIndent=11, bulletIndent=2, spaceAfter=2.5),
    "cell": _p("cell", 7.9, 10.2, font="Times-Roman"),
    "cellb": _p("cellb", 7.9, 10.2, font="Helvetica-Bold"),
    "cellh": _p("cellh", 7.7, 9.8, font="Helvetica-Bold", color=colors.white),
    "setup": _p("setup", 8.4, 11.4),
    "setuph": _p("setuph", 8.4, 11, font="Helvetica-Bold", color=ACCENT),
    "quote": _p("quote", 8.1, 11, font="Times-Italic"),
    "figcap": _p("figcap", 7.5, 9.8, color=MUTED),
    "stat": _p("stat", 14.5, 16, font="Helvetica-Bold", color=ACCENT),
    "statlab": _p("statlab", 7.0, 8.8, color=MUTED),
    "take": _p("take", 9.0, 12, font="Helvetica-Oblique"),
    "takeb": _p("takeb", 7.6, 10, font="Helvetica-Bold", color=WIN),
    "small": _p("small", 7.1, 9.4, color=MUTED),
}

MONO = "<font face='Courier' size='7.5'>{}</font>"
W = A4[0] - 36 * mm


def bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="•") for t in items]


def header(num, title, sub):
    inner = Table([[Paragraph(title, S["slidetitle"])], [Paragraph(sub, S["slidesub"])]],
                  colWidths=[W - 22 * mm], style=TableStyle([
                      ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                      ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                  ]))
    return Table([[Paragraph(num, S["slideno"]), inner]],
                 colWidths=[22 * mm, W - 22 * mm], style=TableStyle([
                     ("BACKGROUND", (0, 0), (-1, -1), INK),
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                     ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                 ]))


def grid(data, widths, centre_from=1):
    st = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, INK),
        ("ALIGN", (centre_from, 0), (-1, -1), "CENTER"),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            st.append(("BACKGROUND", (0, i), (-1, i), BAND))
    return Table(data, colWidths=widths, style=TableStyle(st), hAlign="LEFT")


def statstrip(items):
    cells = [Table([[Paragraph(v, S["stat"])], [Paragraph(lab, S["statlab"])]],
                   style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 1),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
            for v, lab in items]
    w = W / len(items)
    return Table([cells], colWidths=[w] * len(items), style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, RULE),
    ]))


def boxed(rows, title, colour=ACCENT, bg="#f4f7fa"):
    """A labelled definition box: [(term, meaning), ...]."""
    body = [[Paragraph(f"<b>{t}</b>", S["setup"]), Paragraph(d, S["setup"])] for t, d in rows]
    inner = Table(body, colWidths=[34 * mm, W - 52 * mm], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    return Table([[Paragraph(title, S["setuph"])], [inner]], colWidths=[W], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
        ("LINEBEFORE", (0, 0), (0, -1), 3, colour),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]))


def notebox(title, text, colour=ACCENT, bg="#f4f7fa"):
    """A labelled box holding one block of prose."""
    return Table([[Paragraph(title, S["setuph"])], [Paragraph(text, S["setup"])]],
                 colWidths=[W], style=TableStyle([
                     ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                     ("LINEBEFORE", (0, 0), (0, -1), 3, colour),
                     ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                     ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                 ]))


def takeaway(text, colour=WIN):
    return Table([[Paragraph("TAKEAWAY", S["takeb"]), Paragraph(text, S["take"])]],
                 colWidths=[19 * mm, W - 19 * mm], style=TableStyle([
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4f0")),
                     ("LINEBEFORE", (0, 0), (0, -1), 2.5, colour),
                     ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                     ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                 ]))


def banner(text, colour=FAIL, bg="#fdf3f1"):
    return Table([[Paragraph(text, _p("b", 10.5, 14, font="Helvetica-Bold"))]],
                 colWidths=[W], style=TableStyle([
                     ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                     ("LINEBEFORE", (0, 0), (0, -1), 3, colour),
                     ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                     ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                 ]))


# --------------------------------------------------------------------------- #


# Only features a machine can settle without interpreting the language.
# (term, value, what the machine literally looks for)
COUNTABLE = [
    ("They name at least one <b>file</b>", "100%", "text contains <i>x</i>.py / .go / .rs …"),
    ("Either agent asks a <b>question</b>", "9%", "text contains “?”"),
    ("They exchange <b>actual code</b>", "3%",
     "text contains ``` or “def <i>name</i>(” — a lower bound"),
    ("Messages per attempt (median)", "5", "count of messages in the log"),
    ("Whole conversation (median)", "114s", "last timestamp minus first"),
]

# Computed from the two agents' diffs, not from the language.
FORENSICS = [
    ("Clashing attempts examined", "93", "combine failed, both diffs present"),
    ("…the diffs touch a <b>shared file</b>", "100%", "filenames intersected"),
    ("…that file was <b>named in the chat</b>", "100%", "filename matched against the text"),
    ("…they collide on the <b>same line</b>", "90%", "hunk start lines compared"),
    ("…both rewrote the <b>same function</b>", "27%", "“def name(” lines intersected"),
]

ARMS = [
    ("1", "control", "Nothing —<br/>no messaging at all",
     "The baseline. If the talking is doing real work, removing it should hurt.", "13% / 2%"),
    ("2", "free-text", "Whatever they<br/>choose to say",
     "The original condition, repeated here so the other five have something to beat.", "21% / 3%"),
    ("3", "semi-structured", "A filled-in form<br/>about their intent",
     "Tests whether the problem was just <b>sloppiness</b>: forces every message to name its "
     "files and intent, or be rejected.", "16% / 3%"),
    ("4", "plan-handshake", "A split of the files,<br/>agreed up front",
     "Fixes the missing hand-out of work: they must <b>agree who owns which file and wait for a "
     "reply</b> before typing anything.", "20% / 10%"),
    ("5", "designated-coder", "One owner per<br/>shared file",
     "Accepts that a file both need cannot be split, so <b>only one agent writes it</b>; the "
     "other sends a written request instead.", "18% / 58%"),
    ("6", "coauthor-overlap", "<b>The exact merged<br/>code itself</b>",
     "Goes after the clash directly: they agree the shared code word-for-word, then "
     "<b>both type the identical text</b>.", "<b>78% / 69%</b>"),
]

JARGON = [
    ("Combined cleanly", "The two sets of edits went together automatically. <i>Headline measure.</i>"),
    ("Both features work", "After combining, both features pass their tests. <i>Stricter measure.</i>"),
    ("Clash", "Both rewrote the same lines, so the combine refused."),
    ("One carried the pair", "Both features work only because <b>one</b> agent’s copy already "
                             "contained both — not because the two combined."),
]

RESULTS = [
    ("control", "13%", "2%", "87%"),
    ("free-text", "21%", "3%", "79%"),
    ("semi-structured", "16%", "3%", "84%"),
    ("plan-handshake", "20%", "10%", "80%"),
    ("designated-coder", "18%", "58%", "39%"),
    ("coauthor-overlap", "<b>78%</b>", "<b>69%</b>", "<b>17%</b>"),
]


def build():
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=14 * mm, bottomMargin=14 * mm,
                          title="Messaging Protocols — three-slide pack", author="CooperBench")
    doc.addPageTemplates([PageTemplate(id="main", frames=[
        Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")])])
    st = []

    # ===================== SLIDE 1 — SEMANTIC PATTERNS =====================
    st.append(header("SLIDE 1", "What the agents actually said to each other",
                     "703 messages across 147 attempts \u2014 every figure below emitted by one "
                     "script over the raw logs: replication_messages.py"))
    st.append(Spacer(1, 7))
    st.append(notebox(
        "HOW IT IS DONE  —  " + MONO.format("replication_messages.py"),
        "Each message feature is a <b>literal string search</b>: we join an attempt\u2019s messages "
        "into one string and test for a marker \u2014 a filename token such as " +
        MONO.format("loaders.py") + " for \u201cnames a file\u201d, a " + MONO.format("?") +
        " for \u201casks a question\u201d, a code fence or " + MONO.format("def name(") +
        " for \u201csends code\u201d. For every attempt that clashed we then compare the two agents\u2019 "
        "diffs directly \u2014 filenames from " + MONO.format("diff --git") + ", line ranges from " +
        MONO.format("@@ -start,len @@") + " \u2014 which locates each collision in the code itself. "
        "Matching those filenames back against the conversation establishes the central claim "
        "below: the agents had already discussed the file they collided in."))
    st.append(Spacer(1, 6))

    st.append(Paragraph("① Measured from the message logs", S["h2"]))
    st.append(grid(
        [[Paragraph("Measure", S["cellh"]), Paragraph("Value", S["cellh"]),
          Paragraph("What the machine literally looks for", S["cellh"])]] +
        [[Paragraph(t, S["cell"]), Paragraph(f"<b>{v}</b>", S["cell"]), Paragraph(h, S["cell"])]
         for t, v, h in COUNTABLE],
        [W - 96 * mm, 18 * mm, 78 * mm]))
    st.append(Spacer(1, 6))

    st.append(Paragraph("② Measured from the code the agents wrote — the evidence the argument rests on", S["h2"]))
    st.append(grid(
        [[Paragraph("On the attempts that failed to combine", S["cellh"]),
          Paragraph("Value", S["cellh"]), Paragraph("How it is computed", S["cellh"])]] +
        [[Paragraph(t, S["cell"]), Paragraph(f"<b>{v}</b>", S["cell"]), Paragraph(h, S["cell"])]
         for t, v, h in FORENSICS],
        [W - 96 * mm, 18 * mm, 78 * mm]))
    st.append(Paragraph("Each row is a direct comparison of the two diffs.", S["small"]))
    st.append(Spacer(1, 6))

    st.append(Paragraph("One attempt, verbatim "
                        "<font size='7.4' color='#6b7280'>(it clashed)</font>", S["h2"]))
    st.append(Table([[Paragraph(w, S["cellb"]), Paragraph(t, S["quote"])] for w, t in [
        ("agent 2", "\u201cSuggest final combined order: " + MONO.format(
            "(environment, value, attribute, default=None, separator='.', reverse=False)") +
         " \u2014 just append your reverse param after mine.\u201d"),
        ("agent 1", "\u201cmy working copy doesn\u2019t show your separator changes\u2026 we appear to be in "
                    "separate sandboxes. Since each of us submits our own work independently, "
                    "this should be fine \u2014 no actual clobbering.\u201d"),
    ]], colWidths=[16 * mm, W - 16 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ])))
    st.append(Paragraph("Agent 2 spells out the correct combined line; agent 1 agrees; <b>neither "
                        "types it</b>. One documented instance of the mechanism.", S["small"]))
    st.append(Spacer(1, 5))
    st.append(banner("They agree on a <b>description</b> of the answer. "
                     "But the combine is decided by the <b>exact characters</b> they type."))
    st.append(Spacer(1, 5))
    st.append(Paragraph("<b>Scope.</b> Every figure here is a literal count or a diff "
                        "comparison, so each one is reproducible from the logs by rerunning the "
                        "script. Scoring conversations for habits like \u201cboth said they\u2019d add "
                        "theirs last\u201d would need a hand-written phrase list, which belongs to a "
                        "separate coding study with its own reliability check.", S["small"]))

    st.append(PageBreak())

    # ===================== SLIDE 2 — THE PROTOCOLS =========================
    st.append(header("SLIDE 2", "Six sets of rules, and what each one tries to fix",
                     "Each rung forces the pair to agree on more of the final code than the "
                     "rung below"))
    st.append(Spacer(1, 7))

    st.extend(bullets([
        "Same model, tasks, marking and automatic combine throughout — <b>only the cooperation "
        "rules change</b>, so any difference is caused by the rules.",
        "They form a ladder: agree on <b>nothing</b> at the bottom, on <b>the exact code</b> at "
        "the top.",
    ]))
    st.append(Spacer(1, 4))

    st.append(grid(
        [[Paragraph("", S["cellh"]), Paragraph("Rule set", S["cellh"]),
          Paragraph("They must agree on…", S["cellh"]),
          Paragraph("What it is trying to fix", S["cellh"]),
          Paragraph("Combined /<br/>both work", S["cellh"])]] +
        [[Paragraph(f"<b>{n}</b>", S["cell"]), Paragraph(f"<b>{a}</b>", S["cell"]),
          Paragraph(m, S["cell"]), Paragraph(f, S["cell"]), Paragraph(r, S["cell"])]
         for n, a, m, f, r in ARMS],
        [7 * mm, 26 * mm, 30 * mm, W - 88 * mm, 25 * mm], centre_from=4))
    st.append(Spacer(1, 7))

    st.append(Paragraph("Why these six, and why in this order", S["h2"]))
    st.extend(bullets([
        "Slide 1: clashes happen <b>inside</b> a file they already discussed, on the <b>same "
        "line</b>. Agreeing about <i>files</i> is too coarse to prevent them.",
        "So the result is <b>predictable before running anything</b>: rules 1–4 agree only at the "
        "level of files or intentions and should fail; only 5–6 reach the code itself.",
        "Rules 3 and 4 are the useful failures — <b>3</b>: they already named their files every "
        "time, so imposing structure on the message adds nothing. <b>4</b>: a real agreed split "
        "made the code more <i>correct</i>, and no easier to combine.",
    ]))
    st.append(Spacer(1, 5))
    st.append(takeaway("Each rung takes away one more thing the two agents can disagree about. "
                       "The top rung takes away all of them.", ACCENT))
    st.append(Spacer(1, 4))
    st.append(Paragraph("Result column = slide 3\u2019s figures, from " + MONO.format("analyze.py") +
                        " over the run logs.", S["small"]))

    st.append(PageBreak())

    # ===================== SLIDE 3 — THE FINDINGS ==========================
    st.append(header("SLIDE 3", "What happened",
                     "18 tasks chosen because the two features genuinely overlap · "
                     "~1,250 attempts · Claude Sonnet 5"))
    st.append(Spacer(1, 6))
    st.append(boxed(JARGON, "READING THE NUMBERS  —  the two things being measured"))
    st.append(Spacer(1, 6))

    fw = (W - 6 * mm) / 2
    st.append(Table([[
        Image(os.path.join(FIGS, "fig1_endpoints.png"), width=fw, height=fw / 1.42),
        Image(os.path.join(FIGS, "fig2_failure_taxonomy.png"), width=fw, height=fw / 1.35),
    ], [
        Paragraph("<b>How often each rule set worked.</b> Taller is better. Five sit in the same "
                  "low band; only coauthor-overlap breaks out.", S["figcap"]),
        Paragraph("<b>How attempts failed.</b> One bucket each. The clash band dominates "
                  "everywhere except the last rule set.", S["figcap"]),
    ]], colWidths=[fw, fw], style=TableStyle([
        ("VALIGN", (0, 0), (-1, 0), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ])))
    st.append(Spacer(1, 6))

    st.append(grid(
        [[Paragraph("Rule set", S["cellh"]), Paragraph("Combined cleanly", S["cellh"]),
          Paragraph("Both features work", S["cellh"]), Paragraph("Clashed", S["cellh"])]] +
        [[Paragraph(a, S["cell"]), Paragraph(m, S["cell"]),
          Paragraph(b, S["cell"]), Paragraph(c, S["cell"])] for a, m, b, c in RESULTS],
        [W - 102 * mm, 34 * mm, 34 * mm, 34 * mm]))
    st.append(Spacer(1, 6))

    st.append(Paragraph("Key findings", S["h2"]))
    st.extend(bullets([
        "<b>Only one rule set worked.</b> Co-writing the shared code took clean combining "
        "<b>13% → 78%</b> and both-features-working <b>2% → 69%</b> — the only arm to beat the "
        "baseline once you account for having tried six things.",
        "<b>Talking more achieved nothing.</b> Tidier messages, or planning who owns which file, "
        "scored no better than <b>no messaging at all</b> — as slide 1 predicted.",
        "<b>It works by changing what gets typed.</b> The winner produced <b>26</b> byte-identical "
        "results; the other five produced <b>1</b> between them across 1,168 attempts.",
        "<b>Working code ≠ combinable code.</b> designated-coder reaches 58% both-working while "
        "clashing as often as the baseline — one agent quietly carried the pair.",
        "<b>Not solved.</b> The best rule set still clashes 17% of the time and breaks another 10%. "
        "One model, one setup, one style of automatic combine.",
    ]))
    st.append(Spacer(1, 4))
    st.append(takeaway("Rules for cooperation only help when they constrain <b>what the agents "
                       "type</b> — not how much they say to each other."))
    st.append(Spacer(1, 4))
    st.append(Paragraph("<b>Source.</b> All numbers and both figures from " +
                        MONO.format("analyze.py") + " over " + MONO.format("logs/") + ", frozen in "
                        + MONO.format("data/nano_study.json") + "; charts drawn by " +
                        MONO.format("figures.py") + ". \u201cBeats the baseline\u201d = significant under a "
                        "Cochran\u2013Mantel\u2013Haenszel test stratified by task, Holm-corrected across "
                        "the eight comparisons.", S["small"]))

    doc.build(st)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
