#!/usr/bin/env python3
"""
Figures for the messaging-protocol study, built from the frozen analysis dump
data/nano_study.json (produced by the sibling analyze.py). Reading the same
numbers the paper's tables cite means the plotted values can never drift from
the reported results. Requires matplotlib (the analysis itself is stdlib-only).

  Fig 1 — endpoints: merge-clean (primary) vs both-passed (secondary) per arm.
          The talk-only arms sit at the floor; only the structural protocols move.
  Fig 2 — failure taxonomy: where each pair-run lands after the naive merge.
          Shows the mechanism — textual conflict dominates every arm except the
          one that resolves the overlap itself.

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

# --- palette (validated dataviz reference; certified categorical slots) -----
BLUE = "#2a78d6"  # slot 1 — merge-clean / honest pass (the win)
ORANGE = "#eb6834"  # slot 2 — both-passed / functional_fail
YELLOW = "#eda100"  # slot 4 — solo_rescue (evaluation artifact, a caveat)
RED = "#e34948"  # slot 8 — textual_conflict (the dominant failure)
INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"  # axis / labels / missing_patch
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

# study arms, control first — same order and labels as the paper's tables
ARMS = [
    ("nano_control", "control"),
    ("nano_msg", "free-text"),
    ("nano_struct", "semi-struct"),
    ("nano_handshake", "handshake"),
    ("nano_dc", "des. coder"),
    ("nano_coauthor", "coauthor"),
]
# failure taxonomy, ordered good -> bad (a severity scale)
TAX = [
    ("pass", "passed", BLUE),
    ("solo_rescue", "solo-rescue", YELLOW),
    ("functional_fail", "func-fail", ORANGE),
    ("textual_conflict", "conflict", RED),
    ("missing_patch", "no-patch", MUTED),
]


def _style():
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 10,
            "axes.edgecolor": BASELINE,
            "axes.labelcolor": SECONDARY,
            "axes.linewidth": 1.0,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": SECONDARY,
            "ytick.labelcolor": SECONDARY,
            "text.color": INK,
            "axes.titlecolor": INK,
        }
    )


def _bare(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


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

    fig, ax = plt.subplots(figsize=(8.4, 4.3))
    x = list(range(len(ARMS)))
    w = 0.38
    ax.bar([i - w / 2 for i in x], merge, w, color=BLUE, zorder=3,
           label="merge-clean (primary)")
    ax.bar([i + w / 2 for i in x], both, w, color=ORANGE, zorder=3,
           label="both features pass (secondary)")
    for i in x:
        ax.text(i - w / 2, merge[i] + 1.5, f"{merge[i]:.0f}", ha="center", va="bottom",
                fontsize=8.5, color=BLUE)
        ax.text(i + w / 2, both[i] + 1.5, f"{both[i]:.0f}", ha="center", va="bottom",
                fontsize=8.5, color=ORANGE)

    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0", "25", "50", "75", "100%"])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Rate over validated pair-runs")
    ax.set_title("Only structural protocols move the merge — talk does not",
                 fontsize=12, fontweight="bold", loc="left", pad=26)
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0, 1.10),
              handlelength=1.1)
    _bare(ax)
    fig.tight_layout()
    path = os.path.join(OUTDIR, "fig1_endpoints.png")
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


# =========================================================================
# FIGURE 2 — failure taxonomy: where each pair-run lands after the merge
# =========================================================================
def figure2(d):
    tax = d["taxonomy"]
    labels = [lbl for _, lbl in ARMS]
    x = list(range(len(ARMS)))

    # percentages per arm (denominator = all assigned buckets for that arm)
    totals = {k: sum(tax[k].values()) for k, _ in ARMS}
    pct = {
        bucket: [100 * tax[k].get(bucket, 0) / totals[k] for k, _ in ARMS]
        for bucket, _, _ in TAX
    }

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    bottom = [0.0] * len(ARMS)
    for bucket, _, color in TAX:
        vals = pct[bucket]
        # 2px surface gap between stacked segments so adjacent warm hues separate
        ax.bar(x, vals, bottom=bottom, color=color, width=0.68, zorder=3,
               edgecolor=SURFACE, linewidth=1.4)
        for i, v in enumerate(vals):
            if v >= 8:  # direct-label every segment big enough to read
                ax.text(i, bottom[i] + v / 2, f"{v:.0f}", ha="center", va="center",
                        fontsize=8.5, color=SURFACE if color in (RED, BLUE) else INK)
        bottom = [b + v for b, v in zip(bottom, vals)]

    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0", "25", "50", "75", "100%"])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Share of validated pair-runs")
    ax.set_title("Why the merge fails: textual conflict dominates until the overlap is resolved",
                 fontsize=11.5, fontweight="bold", loc="left", pad=30)
    handles = [Patch(facecolor=c, label=lbl) for _, lbl, c in TAX]
    ax.legend(handles=handles, frameon=False, ncol=5, fontsize=8.8, loc="lower center",
              bbox_to_anchor=(0.5, 1.005), handlelength=1.0, columnspacing=1.1,
              handletextpad=0.5)
    _bare(ax)
    fig.tight_layout()
    path = os.path.join(OUTDIR, "fig2_failure_taxonomy.png")
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


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
