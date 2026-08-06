#!/usr/bin/env python3
"""Render the protocol study as a three-page slide pack, one page per slide.

    1. Semantic patterns  — how the agents' messages were read and coded
    2. The protocols      — the six arms and what each one aims to fix
    3. The findings       — the two figures, and what they show

Written to be followable by someone who has never seen the benchmark: the setup
is stated before any result, and every term is defined at the point it is first
used (see SETUP on slide 1 and the JARGON box on slide 3).

Every number quoted is produced by ``replication_messages.py`` (message themes,
patch forensics) and ``analyze.py`` (arm endpoints); this module only lays them
out. No LaTeX toolchain required.

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

SETUP = [
    ("The task", "Two AI agents are each given <b>one feature to add to the same codebase</b> "
                 "— for example, two new options on the same function."),
    ("The catch", "Each works in its <b>own private copy</b>. Neither can see the other's edits. "
                  "They <b>can send each other messages</b> while they work."),
    ("The join", "At the end, their two sets of edits are combined <b>automatically</b>, with no "
                 "human to resolve disagreements."),
    ("What can fail", "If both rewrote the <b>same lines</b>, the automatic combine gives up — a "
                      "<b>clash</b>. The work is done, but it cannot be assembled."),
]

THEMES = [
    ("They name the <b>files</b> they will touch", "100%", "—"),
    ("They actually <b>divide up</b> who owns what (“you take X”)", "1%", "—"),
    ("<b>Both</b> say they will add their change <b>last</b> in the same place", "20%", "97%"),
    ("They agree an order of work their setup cannot deliver "
     "(“I’ll go first”, “layer yours on top”)", "24%", "77%"),
    ("They <b>declare it will combine fine</b> (“additive”, “no overlap”)", "63%", "63%"),
    ("They send each other <b>actual code</b>", "3%", "—"),
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
    ("Combined cleanly", "The two sets of edits went together automatically, with no clash. "
                         "<i>The headline measure.</i>"),
    ("Both features work", "After combining, both agents' features actually pass their tests. "
                           "<i>The stricter measure.</i>"),
    ("Clash", "Both agents rewrote the same lines, so the automatic combine refused."),
    ("One carried the pair", "Both features work, but only because <b>one</b> agent's copy "
                             "happened to contain both — not because the two combined."),
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
                     "Reading all 703 messages, and testing each habit against whether that "
                     "attempt succeeded"))
    st.append(Spacer(1, 7))
    st.append(boxed(SETUP, "THE SETUP  —  what the two agents are being asked to do"))
    st.append(Spacer(1, 7))

    st.append(Paragraph("How we read the messages", S["h2"]))
    st.extend(bullets([
        "We took <b>every message</b> the agents sent — <b>703 of them, across 147 attempts</b> — "
        "and tagged each conversation for recurring habits.",
        "We then <b>linked each conversation to what happened to that attempt</b>, so a habit can "
        "be tested: of the attempts where they said this, how many still ended in a clash?",
        "Finally we compared the talk to the <b>actual edits</b>: for every clash, which file and "
        "which lines the two agents collided on.",
    ]))
    st.append(Spacer(1, 4))

    st.append(grid(
        [[Paragraph("What they habitually do", S["cellh"]),
          Paragraph("Of attempts", S["cellh"]),
          Paragraph("…that still clashed", S["cellh"])]] +
        [[Paragraph(t, S["cell"]), Paragraph(f"<b>{p}</b>", S["cell"]), Paragraph(c, S["cell"])]
         for t, p, c in THEMES],
        [W - 56 * mm, 22 * mm, 34 * mm]))
    st.append(Spacer(1, 6))

    st.append(Paragraph("Where the clashes actually happened", S["h2"]))
    st.append(statstrip([("100%", "clashed inside a file they<br/>had already discussed"),
                         ("90%", "clashed on the very<br/>same line"),
                         ("27%", "both rewrote the same<br/>function’s definition"),
                         ("114s", "median length of the<br/>entire conversation")]))
    st.append(Spacer(1, 6))

    st.append(Paragraph("The whole problem in one exchange "
                        "<font size='7.4' color='#6b7280'>(this attempt ended in a clash)</font>",
                        S["h2"]))
    st.append(Table([[Paragraph(w, S["cellb"]), Paragraph(t, S["quote"])] for w, t in [
        ("agent 2", "“Suggest final combined order: " + MONO.format(
            "(environment, value, attribute, default=None, separator='.', reverse=False)") +
         " — just append your reverse param after mine.”"),
        ("agent 1", "“my working copy doesn’t show your separator changes… we appear to be in "
                    "separate sandboxes. Since each of us submits our own work independently, "
                    "this should be fine — no actual clobbering.”"),
    ]], colWidths=[16 * mm, W - 16 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ])))
    st.append(Paragraph("Agent 2 spells out the correct combined line. Agent 1 agrees to it. "
                        "<b>Neither of them types it.</b> Each writes only its own half into its "
                        "own copy — and the two halves clash.", S["small"]))
    st.append(Spacer(1, 5))
    st.append(banner("They agree on a <b>description</b> of the answer. "
                     "But the combine is decided by the <b>exact characters</b> they type."))

    st.append(PageBreak())

    # ===================== SLIDE 2 — THE PROTOCOLS =========================
    st.append(header("SLIDE 2", "Six sets of rules, and what each one tries to fix",
                     "Each rung forces the pair to agree on more of the final code than the "
                     "rung below"))
    st.append(Spacer(1, 7))

    st.extend(bullets([
        "We re-ran the same task six times over, changing <b>only the rules the agents are given "
        "for working together</b>. Same AI model, same tasks, same marking, same automatic "
        "combine — so any difference is caused by the <b>rules</b>, nothing else.",
        "The six form a ladder: from agreeing on <b>nothing</b> at the bottom, to agreeing on "
        "<b>the exact code</b> at the top.",
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
        "Slide 1 showed the clashes happen <b>inside</b> a file the agents had already talked "
        "about, on the <b>same line</b>. Talking about <i>files</i> is therefore too coarse to "
        "prevent them.",
        "That lets us <b>predict the result before running anything</b>: rules 1–4 only ever get "
        "the pair to agree at the level of files or intentions, so they should fail. Only rules "
        "5–6 reach the actual lines of code, so only they should work.",
        "Rules 3 and 4 are the useful failures. <b>3</b> shows the agents were not being vague — "
        "they already named their files every single time. <b>4</b> shows the problem is not poor "
        "division of labour — forcing a real agreed split made the code more <i>correct</i>, but "
        "no easier to combine.",
    ]))
    st.append(Spacer(1, 5))
    st.append(takeaway("Each rung takes away one more thing the two agents can disagree about. "
                       "The top rung takes away all of them.", ACCENT))

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
        Paragraph("<b>How often each rule set worked.</b> Taller is better. Five of the six sit "
                  "in the same low band — only the last one (coauthor-overlap) breaks out.",
                  S["figcap"]),
        Paragraph("<b>How the attempts failed.</b> Each attempt in exactly one bucket. The dark "
                  "band is clashes: it dominates everywhere except the last rule set.",
                  S["figcap"]),
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
        "<b>The rules matter enormously — but only one set of rules worked.</b> Making the pair "
        "co-write the shared code took clean combining from <b>13% to 78%</b>, and both-features-"
        "working from <b>2% to 69%</b>. It is the only one that beats the baseline once you "
        "account for having tried six things.",
        "<b>Talking more achieved nothing.</b> Tidying up the messages, or planning who owns which "
        "file, left the result no better than <b>giving them no way to talk at all</b> — exactly "
        "as slide 1 predicted.",
        "<b>It works by changing what gets typed, not how much gets said.</b> The winning rule set "
        "produced <b>26</b> cases where both agents wrote byte-for-byte identical code; the other "
        "five produced <b>1</b> between them across more than a thousand attempts.",
        "<b>Working code and combinable code are different problems.</b> designated-coder gets "
        "both features working 58% of the time while still clashing as often as the baseline — "
        "one agent quietly carried the pair.",
        "<b>Still not solved.</b> Even the best rule set clashes 17% of the time, and another 10% "
        "combine cleanly but are broken. One AI model, one setup, one style of automatic combine.",
    ]))
    st.append(Spacer(1, 4))
    st.append(takeaway("Rules for cooperation only help when they constrain <b>what the agents "
                       "type</b> — not how much they say to each other."))

    doc.build(st)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    build()
