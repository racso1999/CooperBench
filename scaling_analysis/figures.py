#!/usr/bin/env python3
"""
Figures for the scaling study, built from the same data/scaling_records.csv the
analysis uses. Reuses analyze.py's calc functions so numbers can never drift
from the reported results. Requires matplotlib (analyze.py itself stays
dependency-free; this is the optional plotting layer).

  Fig 2 — decomposition: correctness, cost, and efficiency vs N (why efficiency
          collapses: flat/declining correctness x rising cost).
  Fig 3 — universality: per-pool efficiency vs N (log-log), every pool a power
          law, degraders vs clean integrators, mean overlaid.

Run:  python3 figures.py            # writes figures/*.png next to this file
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FixedLocator, ScalarFormatter  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import (  # noqa: E402
    calc1_aggregate_by_N,
    calc2_efficiency,
    calc3_power_law,
    calc5_degraders,
    load_records,
    mean,
)

# --- palette (validated dataviz reference; slots used are pre-certified) ---
BLUE = "#2a78d6"  # categorical slot 1
ORANGE = "#eb6834"  # categorical slot 2
INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"  # axis / labels
GRID = "#e1e0d9"  # hairline gridline
BASELINE = "#c3c2b7"  # axis line
SURFACE = "#fcfcfb"  # chart surface

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")


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


def _despine(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _integer_n_axis(ax, ns):
    ax.set_xticks(ns)
    ax.set_xlabel("Agent count  N")


# --- per-pool efficiency series (pool -> {N: efficiency}) ------------------
def per_pool_efficiency(recs):
    from collections import defaultdict

    by_pool = defaultdict(lambda: defaultdict(list))
    for r in recs:
        by_pool[r["pool_id"]][r["N"]].append(r)
    series = {}
    for pool, byn in by_pool.items():
        series[pool] = {
            N: mean([x["score"] for x in g]) / mean([x["cost"] for x in g])
            for N, g in byn.items()
        }
    return series


# =========================================================================
# FIGURE 2 — decomposition (correctness | cost | efficiency)
# =========================================================================
def figure2(recs):
    agg = calc1_aggregate_by_N(recs)
    eff = calc2_efficiency(agg)
    pl = calc3_power_law(eff)
    ns = sorted(agg)

    score = [agg[N]["mean_score"] for N in ns]
    allp = [agg[N]["all_pass_rate"] for N in ns]
    cost = [agg[N]["mean_cost"] for N in ns]
    effv = [eff[N]["efficiency"] for N in ns]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(11.5, 3.9))

    # --- panel (a): correctness -------------------------------------------
    ax1.plot(ns, score, "-o", color=BLUE, lw=2, ms=6, zorder=3, label="Graded score")
    ax1.plot(ns, allp, "-s", color=ORANGE, lw=2, ms=6, zorder=3, label="All-pass rate")
    for x, y in zip(ns, score):
        ax1.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(0, 8),
                     ha="center", fontsize=8, color=BLUE)
    for x, y in zip(ns, allp):
        ax1.annotate(f"{y:.0%}", (x, y), textcoords="offset points", xytext=(0, -14),
                     ha="center", fontsize=8, color=ORANGE)
    ax1.set_ylim(0, 1.05)
    ax1.set_ylabel("Fraction")
    ax1.set_title("(a) Correctness holds or erodes", fontsize=10, loc="left")
    ax1.legend(frameon=False, fontsize=8.5, loc="lower left")
    _despine(ax1)
    _integer_n_axis(ax1, ns)

    # --- panel (b): cost, near-linear -------------------------------------
    ax2.plot(ns, cost, "-o", color=BLUE, lw=2, ms=6, zorder=3, label="Cost / run")
    # linear reference line (OLS through the four means)
    slope, intercept = np.polyfit(ns, cost, 1)
    xline = np.linspace(min(ns), max(ns), 50)
    ax2.plot(xline, slope * xline + intercept, "--", color=MUTED, lw=1.4, zorder=2,
             label=f"Linear ref (${slope:.2f}/agent)")
    for x, y in zip(ns, cost):
        ax2.annotate(f"${y:.2f}", (x, y), textcoords="offset points", xytext=(0, 8),
                     ha="center", fontsize=8, color=BLUE)
    ax2.set_ylim(0, max(cost) * 1.18)
    ax2.set_ylabel("US dollars")
    ax2.set_title("(b) Cost rises near-linearly", fontsize=10, loc="left")
    ax2.legend(frameon=False, fontsize=8.5, loc="upper left")
    _despine(ax2)
    _integer_n_axis(ax2, ns)

    # --- panel (c): efficiency collapse + power-law fit -------------------
    a, b, r2 = pl["a"], pl["b"], pl["r2"]
    xfit = np.linspace(min(ns), max(ns), 100)
    ax3.plot(xfit, a * xfit ** (-b), "--", color=SECONDARY, lw=1.6, zorder=2,
             label=f"$1.28\\,N^{{-1.61}}$")
    ax3.plot(ns, effv, "o", color=BLUE, ms=7, zorder=3, label="Efficiency (solved / \\$)")
    for x, y in zip(ns, effv):
        ax3.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(8, 4),
                     ha="left", fontsize=8, color=BLUE)
    ax3.set_ylim(0, max(effv) * 1.15)
    ax3.set_ylabel("Work solved per dollar")
    ax3.set_title("(c) Efficiency collapses", fontsize=10, loc="left")
    ax3.annotate(f"$R^2 = {r2:.3f}$", (0.96, 0.82), xycoords="axes fraction",
                 ha="right", fontsize=9, color=SECONDARY)
    ax3.legend(frameon=False, fontsize=8.5, loc="upper right")
    _despine(ax3)
    _integer_n_axis(ax3, ns)

    fig.tight_layout()
    path = os.path.join(OUTDIR, "fig2_decomposition.png")
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


# =========================================================================
# FIGURE 3 — universality (per-pool efficiency vs N, log-log)
# =========================================================================
def figure3(recs):
    agg = calc1_aggregate_by_N(recs)
    eff = calc2_efficiency(agg)
    deg = calc5_degraders(recs)["pools"]
    series = per_pool_efficiency(recs)
    ns = sorted(agg)

    fig, ax = plt.subplots(figsize=(6.6, 5.2))

    # thin per-pool lines, coloured by degrader vs clean integrator
    for pool, byn in series.items():
        xs = sorted(byn)
        ys = [byn[N] for N in xs]
        is_deg = deg[pool]["degrades"]
        ax.plot(xs, ys, "-", color=(ORANGE if is_deg else BLUE), lw=1.1,
                alpha=0.55, zorder=2)

    # highlight a clean integrator that still collapses (paper's key example);
    # identified via the legend rather than in-plot text to avoid collisions
    key = "pallets_jinja_task/1621/f1_f5_f6_f9"
    highlight = "#1c5cab"  # darker blue step: distinct from pale pools and black mean
    has_key = key in series
    if has_key:
        xs = sorted(series[key])
        ys = [series[key][N] for N in xs]
        ax.plot(xs, ys, "-o", color=highlight, lw=2.4, ms=5, zorder=4)

    # bold mean-of-all-pools line
    mean_xs = ns
    mean_ys = [eff[N]["efficiency"] for N in ns]
    ax.plot(mean_xs, mean_ys, "-o", color=INK, lw=2.6, ms=6, zorder=5)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_locator(FixedLocator(ns))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_locator(FixedLocator([]))
    ax.set_xlabel("Agent count  N   (log scale)")
    ax.set_ylabel("Work solved per dollar   (log scale)")
    ax.set_title("Efficiency collapses on every pool  (power law = straight line)",
                 fontsize=10.5, loc="left")

    handles = [
        Line2D([0], [0], color=INK, lw=2.6, marker="o", label="Mean (all 14 pools)"),
        Line2D([0], [0], color=BLUE, lw=1.6, label="Clean integrator (8)"),
        Line2D([0], [0], color=ORANGE, lw=1.6, label="Degrader (6)"),
    ]
    if has_key:
        handles.append(
            Line2D([0], [0], color=highlight, lw=2.4, marker="o",
                   label="pallets_jinja/1621 (clean, still collapses)")
        )
    ax.legend(handles=handles, frameon=False, fontsize=9, loc="upper right")
    _despine(ax)

    fig.tight_layout()
    path = os.path.join(OUTDIR, "fig3_universality.png")
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _style()
    recs = load_records()
    print(f"Loaded {len(recs)} runs across {len({r['pool_id'] for r in recs})} pools.")
    p2 = figure2(recs)
    print(f"  wrote {p2}")
    p3 = figure3(recs)
    print(f"  wrote {p3}")


if __name__ == "__main__":
    main()
