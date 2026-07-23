#!/usr/bin/env python3
"""
Figures for the scaling study, built from the same data/scaling_records.csv the
analysis uses. Reuses analyze.py's calc functions so numbers can never drift
from the reported results. Requires matplotlib (analyze.py itself stays
dependency-free; this is the optional plotting layer).

All figures share one monochrome Claude-orange scheme.

  Fig 2 — decomposition, as three separate figures:
            2a correctness vs N, 2b cost vs N, 2c efficiency vs N.

Run:  python3 figures.py            # writes figures/*.png next to this file
"""

import colorsys
import os
import sys

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import (  # noqa: E402
    calc1_aggregate_by_N,
    calc2_efficiency,
    calc3_power_law,
    load_records,
)

# --- Claude-orange monochrome palette (everything is a shade of orange) ----
INK = "#3d1c0a"       # near-black warm brown: text + darkest series
DEEP = "#8f3a14"      # deep burnt orange: emphasis series / fit lines
ORANGE = "#d97757"    # Claude signature orange: primary series
MID = "#e0913f"       # amber orange: secondary series
LIGHT = "#f0c19a"     # pale orange: light background series
MUTED = "#a9846b"     # warm muted brown: axis ticks / reference lines
GRID = "#f2e7db"      # hairline warm grid
BASELINE = "#d9c3b0"  # axis spine
SURFACE = "#fffdfb"   # faint warm off-white surface

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")


def _style():
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            # crisp sans everywhere by default; Charter is applied to the axis
            # labels only (see _fig2_chrome)
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 8,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.5,
            "axes.edgecolor": BASELINE,
            "axes.labelcolor": DEEP,
            "axes.linewidth": 0.9,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "xtick.labelcolor": DEEP,
            "ytick.labelcolor": DEEP,
            "text.color": INK,
            "axes.titlecolor": INK,
        }
    )


# fig2a per-point gradients: colour tracks the fraction value.
#   graded score  — green at high values, sliding into blue-green/teal as the
#                   value dips and back to green as it recovers.
#   all-pass rate — bright orange at high values, deepening to red at low.
def _norm(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _score_shade(v, lo=0.885, hi=0.97):
    t = _norm(v, lo, hi)
    hue = 0.60                      # deep blue throughout
    sat = 0.78 + 0.10 * t           # slight shade variation with the value
    val = 0.60 + 0.22 * t           # higher fraction -> a touch brighter
    return colorsys.hsv_to_rgb(hue, sat, val)


def _allpass_shade(v, lo=0.65, hi=0.92):
    t = _norm(v, lo, hi)
    hue = 0.08 * t                  # 0.08 bright orange (high) -> 0.0 red (low)
    sat = 0.92
    val = 0.72 + 0.25 * t
    return colorsys.hsv_to_rgb(hue, sat, val)


# one hue per series (related points share a colour); only brightness and
# saturation track the value, so a series reads as a single colour, not a ramp.
def _mono_shade(v, hue, lo, hi):
    t = _norm(v, lo, hi)
    return colorsys.hsv_to_rgb(hue, 0.45 + 0.45 * t, 0.55 + 0.40 * t)


COST_HUE = 0.74   # violet — fig2b cost markers
EFF_HUE = 0.42    # green  — fig2c efficiency markers


# two-sided t critical values at 95% by degrees of freedom (small-sample honest)
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
         8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160}


def _correctness_ci(recs):
    """Per-N 95% error bars for fig2a.
    Graded score: CI of the mean, clustered by pool (t across the pool means, so
    the real replication unit is the pool, not the individual run).
    All-pass rate: Wilson 95% interval for a binomial proportion.
    Returns {N: {score_hw, allp_lo, allp_hi}} as distances from each point."""
    from collections import defaultdict

    by_n = defaultdict(list)
    for r in recs:
        by_n[r["N"]].append(r)
    out = {}
    for N, g in by_n.items():
        by_pool = defaultdict(list)
        for r in g:
            by_pool[r["pool_id"]].append(r["score"])
        pool_means = np.array([np.mean(v) for v in by_pool.values()])
        k = len(pool_means)
        if k > 1:
            sem = pool_means.std(ddof=1) / np.sqrt(k)
            score_hw = _T975.get(k - 1, 1.96) * sem
        else:
            score_hw = 0.0

        n = len(g)
        p = sum(1 for r in g if r["all_passed"]) / n
        z = 1.96
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        out[N] = {"score_hw": score_hw,
                  "allp_lo": p - (center - half),
                  "allp_hi": (center + half) - p,
                  "n_pools": k}
    return out


def _cost_ci(recs):
    """Per-N 95% CI of the mean cost, clustered by pool (same construct as the
    graded-score bars in fig2a). Returns {N: {cost_hw, n_pools}}."""
    from collections import defaultdict

    by_n = defaultdict(list)
    for r in recs:
        by_n[r["N"]].append(r)
    out = {}
    for N, g in by_n.items():
        by_pool = defaultdict(list)
        for r in g:
            by_pool[r["pool_id"]].append(r["cost"])
        pool_means = np.array([np.mean(v) for v in by_pool.values()])
        k = len(pool_means)
        sem = pool_means.std(ddof=1) / np.sqrt(k) if k > 1 else 0.0
        out[N] = {"cost_hw": _T975.get(k - 1, 1.96) * sem, "n_pools": k}
    return out


def _save(fig, name, facecolor=SURFACE):
    path = os.path.join(OUTDIR, name)
    fig.savefig(path, dpi=400, bbox_inches="tight", facecolor=facecolor)
    plt.close(fig)
    return path


# --- shared fig2a/b/c styling ---------------------------------------------
def _fig2_chrome(fig, ax, ns, ylabel):
    """Greyscale chrome, small black wording, tight axis labels, no title — the
    look dialled in on fig2a. Axis labels use Charter; everything else (ticks,
    legend, value labels) stays in the crisp sans default."""
    ax.set_ylabel(ylabel, fontsize=5.3, labelpad=0, color="black", fontname="Charter")
    ax.set_xlabel("Agent count  N", fontsize=5.3, labelpad=-3, color="black",
                  fontname="Charter")
    ax.set_xticks(ns)
    ax.tick_params(axis="both", labelsize=5, labelcolor="black", color="black",
                   width=0.5)
    fig.set_facecolor("white")
    ax.set_facecolor("white")
    ax.grid(True, color="0.8", linewidth=0.35, alpha=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("black")
        ax.spines[side].set_linewidth(0.5)


def _fig2_legend(ax, handles=None, loc="lower left", bbox=(0.03, 0.04)):
    """Small boxed legend tucked into an empty corner of the plot area."""
    kw = dict(loc=loc, bbox_to_anchor=bbox, ncol=1, frameon=True,
              fontsize=5, handlelength=1.4, borderpad=0.4, labelspacing=0.3,
              handletextpad=0.5, framealpha=0.95, edgecolor="0.7")
    leg = ax.legend(handles=handles, **kw) if handles is not None else ax.legend(**kw)
    leg.get_frame().set_linewidth(0.4)
    for txt in leg.get_texts():
        txt.set_color("black")
        txt.set_fontsize(5)
    return leg


# =========================================================================
# FIGURE 2a — correctness vs N
# =========================================================================
def figure2a(recs):
    agg = calc1_aggregate_by_N(recs)
    ns = sorted(agg)
    score = [agg[N]["mean_score"] for N in ns]
    allp = [agg[N]["all_pass_rate"] for N in ns]

    fig, ax = plt.subplots(figsize=(3.7, 3.3))
    # thin black connecting lines; markers drawn separately so each point can
    # carry its own fraction-scaled colour (green = score, orange = all-pass)
    ax.plot(ns, score, "-", color="black", lw=0.7, zorder=3)
    ax.plot(ns, allp, "-", color="black", lw=0.7, zorder=3)
    # 95% CI error bars (score: pool-clustered t; all-pass: Wilson)
    ci = _correctness_ci(recs)
    ax.errorbar(ns, score, yerr=[ci[N]["score_hw"] for N in ns], fmt="none",
                ecolor="0.4", elinewidth=0.7, capsize=2, capthick=0.7, zorder=3)
    ax.errorbar(ns, allp, yerr=[[ci[N]["allp_lo"] for N in ns],
                                [ci[N]["allp_hi"] for N in ns]], fmt="none",
                ecolor="0.4", elinewidth=0.7, capsize=2, capthick=0.7, zorder=3)
    ax.scatter(ns, score, s=32, marker="o", zorder=4, linewidths=0.3,
               edgecolors="black", c=[_score_shade(v) for v in score])
    ax.scatter(ns, allp, s=32, marker="s", zorder=4, linewidths=0.3,
               edgecolors="black", c=[_allpass_shade(v) for v in allp])
    # labels offset to the side so they clear the vertical error bars
    for x, y in zip(ns, score):
        ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(8, 4),
                    ha="left", fontsize=4.7, color="black", fontname="Helvetica")
    for x, y in zip(ns, allp):
        ax.annotate(f"{y:.0%}", (x, y), textcoords="offset points", xytext=(8, -8),
                    ha="left", fontsize=4.7, color="black", fontname="Helvetica")
    # pool count behind each N's error bars (drives the CI width)
    for N in ns:
        ax.text(N, 1.10, f"{ci[N]['n_pools']} pools", ha="center", va="bottom",
                fontsize=4.3, color="0.45", fontname="Helvetica")
    ax.set_ylim(0, 1.16)
    handles = [
        Line2D([0], [0], color="black", lw=0.7, marker="o", markersize=5,
               markerfacecolor=_score_shade(0.95), markeredgecolor="black",
               markeredgewidth=0.3, label="Graded score"),
        Line2D([0], [0], color="black", lw=0.7, marker="s", markersize=5,
               markerfacecolor=_allpass_shade(0.88), markeredgecolor="black",
               markeredgewidth=0.3, label="All-pass rate"),
    ]
    _fig2_chrome(fig, ax, ns, "Fraction")
    _fig2_legend(ax, handles)
    return _save(fig, "fig2a_correctness.png", facecolor="white")


# =========================================================================
# FIGURE 2b — cost vs N (near-linear)
# =========================================================================
def figure2b(recs):
    agg = calc1_aggregate_by_N(recs)
    ns = sorted(agg)
    cost = [agg[N]["mean_cost"] for N in ns]

    fig, ax = plt.subplots(figsize=(3.7, 3.3))
    slope, intercept = np.polyfit(ns, cost, 1)
    xline = np.linspace(min(ns), max(ns), 50)
    ax.plot(xline, slope * xline + intercept, "--", color="0.5", lw=1.0, zorder=2)
    ax.plot(ns, cost, "-", color="black", lw=0.7, zorder=3)
    # 95% CI of mean cost, clustered by pool (matches fig2a)
    ci = _cost_ci(recs)
    ax.errorbar(ns, cost, yerr=[ci[N]["cost_hw"] for N in ns], fmt="none",
                ecolor="0.4", elinewidth=0.7, capsize=2, capthick=0.7, zorder=3)
    # one hue (violet); markers deepen/brighten with cost but read as one series
    lo, hi = min(cost), max(cost)
    cvals = [_mono_shade(c, COST_HUE, lo, hi) for c in cost]
    ax.scatter(ns, cost, s=34, marker="o", zorder=4, linewidths=0.3,
               edgecolors="black", c=cvals)
    for x, y in zip(ns, cost):
        ax.annotate(f"${y:.2f}", (x, y), textcoords="offset points", xytext=(7, -9),
                    ha="left", fontsize=4.7, color="black", fontname="Helvetica")
    # pool count above each error bar (drives the CI width)
    for N, y in zip(ns, cost):
        ax.annotate(f"{ci[N]['n_pools']} pools", (N, y + ci[N]["cost_hw"]),
                    textcoords="offset points", xytext=(0, 4), ha="center",
                    va="bottom", fontsize=4.3, color="0.45", fontname="Helvetica")
    top = max(c + ci[N]["cost_hw"] for N, c in zip(ns, cost))
    ax.set_ylim(0, top * 1.16)
    _fig2_chrome(fig, ax, ns, "US dollars")
    return _save(fig, "fig2b_cost.png", facecolor="white")


# =========================================================================
# FIGURE 2c — efficiency vs N (collapse + power-law fit)
# =========================================================================
def figure2c(recs):
    agg = calc1_aggregate_by_N(recs)
    eff = calc2_efficiency(agg)
    pl = calc3_power_law(eff)
    ns = sorted(agg)
    effv = [eff[N]["efficiency"] for N in ns]
    a, b, r2 = pl["a"], pl["b"], pl["r2"]

    fig, ax = plt.subplots(figsize=(3.7, 3.3))
    xfit = np.linspace(min(ns), max(ns), 100)
    ax.plot(xfit, a * xfit ** (-b), "--", color="0.45", lw=1.0, zorder=2)
    # one hue (green); markers fade with the collapse but read as one series
    lo, hi = min(effv), max(effv)
    cvals = [_mono_shade(e, EFF_HUE, lo, hi) for e in effv]
    ax.scatter(ns, effv, s=44, marker="o", zorder=3, linewidths=0.3,
               edgecolors="black", c=cvals)
    for x, y in zip(ns, effv):
        ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(7, 3),
                    ha="left", fontsize=4.7, color="black", fontname="Helvetica")
    ax.set_ylim(0, max(effv) * 1.15)
    handles = [
        Line2D([0], [0], color="0.45", lw=1.0, ls="--",
               label=f"${a:.2f}\\,N^{{-{b:.1f}}}$"),
        Line2D([0], [0], color="black", lw=0, marker="o", markersize=6,
               markerfacecolor=_mono_shade(hi, EFF_HUE, lo, hi),
               markeredgecolor="black", markeredgewidth=0.3,
               label="Efficiency (solved / \\$)"),
    ]
    _fig2_chrome(fig, ax, ns, "Work solved per dollar")
    _fig2_legend(ax, handles)
    return _save(fig, "fig2c_efficiency.png", facecolor="white")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _style()
    recs = load_records()
    print(f"Loaded {len(recs)} runs across {len({r['pool_id'] for r in recs})} pools.")
    for fn in (figure2a, figure2b, figure2c):
        print(f"  wrote {fn(recs)}")


if __name__ == "__main__":
    main()
