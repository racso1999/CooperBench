#!/usr/bin/env python3
"""
Figures for the messaging-protocol study, built from the frozen analysis dump
data/nano_study.json (produced by the sibling analyze.py). Reading the same
numbers the paper's tables cite means the plotted values can never drift from
the reported results. Requires matplotlib (the analysis itself is stdlib-only).

Styled to match the scaling study's figures (masters_thesis/scaling_analysis):
compact white panels, thin black left/bottom spines, a faint warm grid, tiny
Charter axis labels with direct value labels in Helvetica, a small boxed corner
legend, no in-figure title, and one warm Claude-orange palette throughout.

  Fig 1 — endpoints: merge-clean (primary) vs both-passed (secondary) per arm.
          The talk-only arms sit at the floor; only the structural protocols move.
  Fig 2 — failure taxonomy: where each pair-run lands after the naive merge,
          on a pale-to-dark severity ramp. Textual conflict (deep) dominates
          every arm except the one that resolves the overlap itself.

Run:  python3 figures.py            # writes figures/*.png next to this file

Regenerate the frozen data first if logs/ changed:
  uv run python masters_thesis/protocol_analysis/analyze.py
"""

import json
import os

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "nano_study.json")
OUTDIR = os.path.join(HERE, "figures")

# --- Claude-orange warm palette (shared with scaling_analysis/figures.py) ----
INK = "#3d1c0a"       # near-black warm brown: text + darkest segment
DEEP = "#8f3a14"      # deep burnt orange: emphasis / worst-failure segment
ORANGE = "#d97757"    # Claude signature orange: primary series
MID = "#e0913f"       # amber orange: secondary series
LIGHT = "#f0c19a"     # pale orange: best-outcome / light series
MUTED = "#a9846b"     # warm muted brown: axis ticks
BASELINE = "#d9c3b0"  # axis spine
SURFACE = "#fffdfb"   # faint warm off-white surface

# study arms, control first — same order and labels as the paper's tables
ARMS = [
    ("nano_control", "control"),
    ("nano_msg", "free-text"),
    ("nano_struct", "semi-struct"),
    ("nano_handshake", "handshake"),
    ("nano_dc", "des. coder"),
    ("nano_coauthor", "coauthor"),
]
# failure taxonomy, ordered good -> bad on a pale-to-dark severity ramp
TAX = [
    ("pass", "passed", LIGHT),
    ("solo_rescue", "solo-rescue", MID),
    ("functional_fail", "func-fail", ORANGE),
    ("textual_conflict", "conflict", DEEP),
    ("missing_patch", "no-patch", INK),
]
# which segment colours need white (rather than black) direct labels
_DARK = {DEEP, INK}


def _style():
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            # crisp sans everywhere by default; Charter is applied to the axis
            # labels only (see _chrome)
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 8,
            "axes.edgecolor": BASELINE,
            "axes.labelcolor": DEEP,
            "axes.linewidth": 0.9,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": DEEP,
            "ytick.labelcolor": DEEP,
            "text.color": INK,
        }
    )


# --- shared chrome (mirrors scaling_analysis' _fig2_chrome, categorical x) --
def _chrome(fig, ax, labels, ylabel):
    """Greyscale chrome, small black wording, tight axis labels, no title — the
    look dialled in on the scaling figures. The y-axis label uses Charter;
    everything else (ticks, legend, value labels) stays in the crisp sans
    default. x is categorical (the study arms), so there is no x-axis label."""
    ax.set_ylabel(ylabel, fontsize=5.3, labelpad=1, color="black", fontname="Charter")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0", "25", "50", "75", "100%"])
    ax.tick_params(axis="both", labelsize=5.2, labelcolor="black", color="black",
                   width=0.5)
    fig.set_facecolor("white")
    ax.set_facecolor("white")
    ax.grid(axis="y", color="0.8", linewidth=0.35, alpha=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("black")
        ax.spines[side].set_linewidth(0.5)


def _legend(ax, handles, loc="upper left", bbox=(0.03, 0.97), ncol=1):
    """Small boxed legend, matching the scaling figures' corner legend."""
    leg = ax.legend(handles=handles, loc=loc, bbox_to_anchor=bbox, ncol=ncol,
                    frameon=True, fontsize=5, handlelength=1.4, borderpad=0.4,
                    labelspacing=0.3, handletextpad=0.5, columnspacing=1.0,
                    framealpha=0.95, edgecolor="0.7")
    leg.get_frame().set_linewidth(0.4)
    for txt in leg.get_texts():
        txt.set_color("black")
        txt.set_fontsize(5)
    return leg


def _save(fig, name):
    path = os.path.join(OUTDIR, name)
    fig.savefig(path, dpi=400, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def load():
    with open(DATA) as f:
        return json.load(f)


# =========================================================================
# FIGURE 1 — endpoints: merge-clean (primary) vs both-passed (secondary)
# =========================================================================
def figure1(d):
    per = d["perarm"]
    labels = [lbl for _, lbl in ARMS]
    merge = [100 * per[k]["mergeok"] / per[k]["n"] for k, _ in ARMS]
    both = [100 * per[k]["both"] / per[k]["n"] for k, _ in ARMS]

    fig, ax = plt.subplots(figsize=(4.6, 3.3))
    x = list(range(len(ARMS)))
    w = 0.40
    # signature orange = the primary win; pale orange = the secondary endpoint
    ax.bar([i - w / 2 for i in x], merge, w, color=ORANGE, edgecolor="black",
           linewidth=0.4, zorder=3)
    ax.bar([i + w / 2 for i in x], both, w, color=LIGHT, edgecolor="black",
           linewidth=0.4, zorder=3)
    for i in x:
        ax.annotate(f"{merge[i]:.0f}", (i - w / 2, merge[i]),
                    textcoords="offset points", xytext=(0, 2), ha="center",
                    va="bottom", fontsize=4.7, color="black", fontname="Helvetica")
        ax.annotate(f"{both[i]:.0f}", (i + w / 2, both[i]),
                    textcoords="offset points", xytext=(0, 2), ha="center",
                    va="bottom", fontsize=4.7, color="black", fontname="Helvetica")

    handles = [
        Patch(facecolor=ORANGE, edgecolor="black", linewidth=0.4,
              label="merge-clean (primary)"),
        Patch(facecolor=LIGHT, edgecolor="black", linewidth=0.4,
              label="both features pass (secondary)"),
    ]
    _chrome(fig, ax, labels, "Rate over validated pair-runs")
    _legend(ax, handles, loc="upper left", bbox=(0.03, 0.97))
    return _save(fig, "fig1_endpoints.png")


# =========================================================================
# FIGURE 2 — failure taxonomy: where each pair-run lands after the merge
# =========================================================================
def figure2(d):
    tax = d["taxonomy"]
    labels = [lbl for _, lbl in ARMS]
    x = list(range(len(ARMS)))

    # percentages per arm (denominator = all assigned buckets for that arm)
    totals = {k: sum(tax[k].get(b, 0) for b, _, _ in TAX) for k, _ in ARMS}
    pct = {
        bucket: [100 * tax[k].get(bucket, 0) / totals[k] for k, _ in ARMS]
        for bucket, _, _ in TAX
    }

    fig, ax = plt.subplots(figsize=(4.6, 3.3))
    bottom = [0.0] * len(ARMS)
    for bucket, _, color in TAX:
        vals = pct[bucket]
        ax.bar(x, vals, bottom=bottom, color=color, width=0.66, zorder=3,
               edgecolor="black", linewidth=0.4)
        for i, v in enumerate(vals):
            if v >= 8:  # direct-label every segment big enough to read
                ax.text(i, bottom[i] + v / 2, f"{v:.0f}", ha="center", va="center",
                        fontsize=4.7, fontname="Helvetica",
                        color="white" if color in _DARK else "black")
        bottom = [b + v for b, v in zip(bottom, vals)]

    handles = [Patch(facecolor=c, edgecolor="black", linewidth=0.4, label=lbl)
               for _, lbl, c in TAX]
    _chrome(fig, ax, labels, "Share of validated pair-runs")
    # 100%-stacked leaves no empty corner, so seat the legend just above the axes
    _legend(ax, handles, loc="lower center", bbox=(0.5, 1.01), ncol=5)
    return _save(fig, "fig2_failure_taxonomy.png")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _style()
    d = load()
    print(f"Loaded {len(d['kept'])} validated pairs "
          f"({len(d['dropped'])} dropped by pre-registered exclusion).")
    print(f"  wrote {figure1(d)}")
    print(f"  wrote {figure2(d)}")


if __name__ == "__main__":
    main()
