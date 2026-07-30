#!/usr/bin/env python3
"""
Figures for the leader-topology (supervised) scaling study, built from the same
data/records.csv the analysis uses. Reuses analyze_leader.py's calc
functions so numbers can never drift from the reported results, and the chrome
helpers from figures.py so this suite matches fig 2a-2e exactly.

  Fig 3 — supervised vs flat, as four figures:
            3a efficiency vs team size (+ power-law fits, the crossover),
            3b correctness vs team size (the opposing all-pass trends),
            3c cost accounts (where each topology spends),
            3d wall-clock vs team size.

Run:  python3 figures_leader.py     # writes figures/fig3*.png next to this file
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import (  # noqa: E402
    calc1_aggregate,
    calc2_efficiency,
    calc3_power_law,
    calc4_outcome_mix,
    calc6_accounts,
    calc7_time,
    load_accounts,
    load_records,
)

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")

# --- house style -----------------------------------------------------------
# palette constants the chrome below expects (from the fig2 suite)
INK = "#3d1c0a"       # near-black warm brown: text
DEEP = "#8f3a14"      # deep burnt orange: axis labels
MUTED = "#a9846b"     # warm muted brown: axis ticks
BASELINE = "#d9c3b0"  # axis spine
SURFACE = "#fffdfb"   # faint warm off-white surface

# Kept verbatim in sync with ../scaling_analysis/figures.py so fig 3 reads as a
# sibling of fig 2. Duplicated rather than imported because both studies ship a
# module named `figures` (and one named `analyze`), so cross-importing collides;
# self-containment is the same property the fig2 suite advertises.

# two-sided t critical values at 95% by degrees of freedom (small-sample honest)
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
         8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160}


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


def _fig2_chrome(fig, ax, ns, ylabel):
    """Greyscale chrome, small black wording, tight axis labels, no title — the
    look dialled in on fig2a. Axis labels use Charter; everything else (ticks,
    legend, value labels) stays in the crisp sans default."""
    ax.set_ylabel(ylabel, fontsize=5.3, labelpad=0, color="black", fontname="Charter")
    # labelpad: the fig2 suite tucks this to -3, which collides with the tick
    # labels on the fig3 axes (log scale on 3a, paired bars on 3c). +2 across
    # the whole fig3 suite keeps it clear and internally consistent.
    ax.set_xlabel("Agent count  N", fontsize=5.3, labelpad=2, color="black",
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
  # noqa: E402

# --- arm colours ----------------------------------------------------------
# Two categorical slots (topology identity, not magnitude), validated with the
# dataviz six-checks: CVD dE 17.4 (target 8), normal-vision dE 28.0 (floor 15),
# contrast 4.8 / 6.9 vs white. FLAT is the paper's sea blue snapped one step up
# in chroma — the fig2d value (#2f7d9a, C=0.087) sits under the 0.10 chroma
# floor and reads gray in isolation.
FLAT = "#1b7ba0"    # flat peer topology
LEADER = "#b01e28"  # supervised topology
# fig2d's four-account ramp, reused verbatim so fig3c reads as its sibling:
# cool = the base work you would pay anyway, warm = the coordination tax.
ACCOUNTS = [("Context", "context", "#cfe6ef"), ("Task", "task", "#1b7ba0"),
            ("Comm", "comm", "#ef8080"), ("Rework", "rework", "#b01e28")]


def _ci(recs, arm, field, agents):
    """95% CI half-width of the mean, clustered by pool (matches fig2a/2b)."""
    from collections import defaultdict
    by_pool = defaultdict(list)
    for r in recs:
        if r["arm"] == arm and r["agents"] == agents and r.get(field) is not None:
            by_pool[r["pool_id"]].append(r[field])
    if not by_pool:
        return 0.0
    pool_means = np.array([np.mean(v) for v in by_pool.values()])
    k = len(pool_means)
    if k < 2:
        return 0.0
    return _T975.get(k - 1, 1.96) * pool_means.std(ddof=1) / np.sqrt(k)


def _save(fig, name, facecolor="white"):
    """Local save so figures land in THIS study's figures/ dir."""
    path = os.path.join(OUTDIR, name)
    fig.savefig(path, dpi=400, bbox_inches="tight", facecolor=facecolor)
    plt.close(fig)
    return path


def _arm_points(agg, arm, key):
    ns = sorted(n for (a, n) in agg if a == arm)
    return ns, [agg[(arm, n)][key] for n in ns]


# =========================================================================
# FIGURE 3a — efficiency vs team size, both topologies (THE headline)
# =========================================================================
# Work solved per dollar against team size, with each arm's power-law fit.
# The exponent is the point: b=1 is the floor (cost strictly proportional to
# head-count, no coordination waste), so flat's b=1.61 is super-proportional
# waste while the supervisor's b=1.10 sits almost exactly at the floor. The
# curves cross, so the supervisor is worse small and better large.
def figure3a(recs):
    agg = calc1_aggregate(recs)
    eff = calc2_efficiency(agg)

    fig, ax = plt.subplots(figsize=(3.7, 3.3))
    handles = []
    # per-endpoint label offsets, hand-placed to clear the other arm's marker
    OFF = {"flat": [(-2, 7), (-16, -3)], "leader": [(-17, -3), (2, 7)]}
    for arm, colour, label in (("flat", FLAT, "Flat peers"), ("leader", LEADER, "Supervised")):
        pl = calc3_power_law(eff, arm)
        ns = [n for n, _ in pl["points"]]
        ys = [e for _, e in pl["points"]]
        xfit = np.linspace(min(ns), max(ns), 100)
        ax.plot(xfit, pl["a"] * xfit ** (-pl["b"]), "--", color=colour, lw=1.0, alpha=0.6, zorder=2)
        ax.scatter(ns, ys, s=34, marker="o", zorder=4, linewidths=0.3, edgecolors="black", c=colour)
        # selective labels: endpoints only — the fits carry the shape between them
        for (x, y), off in zip(((ns[0], ys[0]), (ns[-1], ys[-1])), OFF[arm]):
            ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=off,
                        ha="center", fontsize=4.6, color="black", fontname="Helvetica")
        handles.append(Line2D([0], [0], color=colour, lw=1.0, ls="--", marker="o", markersize=5,
                              markerfacecolor=colour, markeredgecolor="black", markeredgewidth=0.3,
                              label=f"{label}   $\\propto N^{{-{pl['b']:.2f}}}$"))
    # log-log: a power law is a straight line, so the two exponents are two
    # slopes and the crossover is where they intersect.
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([1, 2, 3, 4, 5]); ax.set_xticklabels(["1", "2", "3", "4", "5"])
    ax.set_yticks([0.1, 0.2, 0.5, 1.0]); ax.set_yticklabels(["0.1", "0.2", "0.5", "1.0"])
    ax.minorticks_off()
    # mark where the supervised curve overtakes the flat one
    fa, fb = calc3_power_law(eff, "flat")["a"], calc3_power_law(eff, "flat")["b"]
    la, lb = calc3_power_law(eff, "leader")["a"], calc3_power_law(eff, "leader")["b"]
    xc = (la / fa) ** (1.0 / (lb - fb))
    if 1 < xc < 5.6:
        ax.axvline(xc, color="0.6", lw=0.5, ls=":", zorder=1)
        ax.annotate(f"crossover\nN={xc:.1f}", (xc, 0.105), textcoords="offset points", xytext=(4, 0),
                    ha="left", va="bottom", fontsize=4.3, color="0.35", fontname="Helvetica")
    ax.set_ylim(0.085, 1.55)  # headroom so endpoint labels clear the axes
    _fig2_chrome(fig, ax, [1, 2, 3, 4, 5], "Work solved per dollar  (log)")
    _fig2_legend(ax, handles, loc="lower left", bbox=(0.03, 0.04))
    return _save(fig, "fig3a_efficiency_topology.png", facecolor="white")


# =========================================================================
# FIGURE 3b — correctness vs team size (the opposing trends)
# =========================================================================
# Strict all-pass rate: the probability the team ships a fully-correct
# integration. The two topologies move in OPPOSITE directions with team size —
# flat degrades monotonically, supervised improves — so they cross.
def figure3b(recs):
    agg = calc1_aggregate(recs)

    fig, ax = plt.subplots(figsize=(3.7, 3.3))
    handles = []
    for arm, colour, label, ly in (("flat", FLAT, "Flat peers", 7), ("leader", LEADER, "Supervised", -11)):
        ns, ys = _arm_points(agg, arm, "all_pass_rate")
        # Wilson 95% interval for a binomial proportion (matches fig2a)
        los, his = [], []
        for n, p in zip(ns, ys):
            k = agg[(arm, n)]["n_runs"]
            z = 1.96
            den = 1 + z * z / k
            centre = (p + z * z / (2 * k)) / den
            half = z * np.sqrt(p * (1 - p) / k + z * z / (4 * k * k)) / den
            los.append(max(p - (centre - half), 0)); his.append(max((centre + half) - p, 0))
        ax.errorbar(ns, ys, yerr=[los, his], fmt="none", ecolor="0.45",
                    elinewidth=0.7, capsize=2, capthick=0.7, zorder=3)
        ax.plot(ns, ys, "-", color="black", lw=0.7, zorder=3)
        ax.scatter(ns, ys, s=34, marker="o", zorder=4, linewidths=0.3, edgecolors="black", c=colour)
        for x, y in zip(ns, ys):
            ax.annotate(f"{y:.0%}", (x, y), textcoords="offset points", xytext=(7, ly),
                        ha="left", fontsize=4.5, color="black", fontname="Helvetica")
        handles.append(Line2D([0], [0], color="black", lw=0.7, marker="o", markersize=5,
                              markerfacecolor=colour, markeredgecolor="black", markeredgewidth=0.3, label=label))
    ax.set_ylim(0, 1.08)
    _fig2_chrome(fig, ax, [1, 2, 3, 4, 5], "All-pass rate (fully-correct integration)")
    _fig2_legend(ax, handles, loc="lower left", bbox=(0.03, 0.04))
    return _save(fig, "fig3b_correctness_topology.png", facecolor="white")


# =========================================================================
# FIGURE 3c — cost accounts by topology (where each one spends)
# =========================================================================
# Small multiples: one panel per topology, shared y-axis, so the two are
# compared by bar height rather than by a texture overlaid on the fills.
# Within each bar, fig2d's ramp: cool = base work you would pay anyway
# (context floor, then task), warm = the coordination tax (comm + the rework
# it provokes). The label on the warm cap is that tax's share of the run.
def figure3c(accts):
    dec = calc6_accounts(accts)
    panels = [("flat", "Flat peers"), ("leader", "Supervised")]
    ymax = max(v["total"] for v in dec.values()) * 1.16

    fig, axes = plt.subplots(1, 2, figsize=(5.6, 3.3), sharey=True)
    for ax, (arm, title) in zip(axes, panels):
        xs = sorted(n for (a, n) in dec if a == arm)
        bottoms = {n: 0.0 for n in xs}
        for _label, key, colour in ACCOUNTS:
            hs = [dec[(arm, n)][key] for n in xs]
            ax.bar(xs, hs, bottom=[bottoms[n] for n in xs], width=0.62,
                   color=colour, edgecolor="black", linewidth=0.4, zorder=3)
            for n, h in zip(xs, hs):
                bottoms[n] += h
        for n in xs:
            tot = dec[(arm, n)]["total"]
            ax.annotate(f"${tot:.2f}", (n, tot), textcoords="offset points", xytext=(0, 3),
                        ha="center", va="bottom", fontsize=4.4, color="black", fontname="Helvetica")
            cap = dec[(arm, n)]["comm"] + dec[(arm, n)]["rework"]
            if cap > 0:
                ax.annotate(f"{dec[(arm, n)]['comm_rework_share']*100:.0f}%", (n, tot - cap / 2),
                            ha="center", va="center", fontsize=4.6, color=INK, fontweight="bold",
                            fontname="Helvetica",
                            bbox=dict(boxstyle="round,pad=0.16", fc="white", ec="none", alpha=0.75))
        ax.set_ylim(0, ymax)
        _fig2_chrome(fig, ax, sorted({n for (_a, n) in dec}), "US dollars")
        ax.set_title(title, fontsize=5.6, color="black", fontname="Charter", pad=3)
    axes[1].set_ylabel("")  # shared axis: label once, on the left
    # One centred x-label for the pair rather than the same words twice.
    for ax in axes:
        ax.set_xlabel("")
    fig.supxlabel("Agent count  N", fontsize=5.3, color="black", fontname="Charter", y=0.02)
    handles = [Patch(facecolor=c, edgecolor="black", linewidth=0.4, label=lbl) for lbl, _k, c in ACCOUNTS]
    _fig2_legend(axes[0], handles, loc="upper left", bbox=(0.02, 0.98))
    fig.subplots_adjust(wspace=0.08)
    return _save(fig, "fig3c_accounts_topology.png", facecolor="white")


# =========================================================================
# FIGURE 3d — wall-clock to completion by topology
# =========================================================================
# Observed wall-clock (a run ends when its slowest agent does) against the
# dashed ideal of perfect work-sharing, T1/N, anchored at the flat solo mean.
# Both topologies rise where the ideal falls; supervision is the slower of the
# two at every size, and its gap widens.
def figure3d(recs):
    t = calc7_time(recs)
    fig, ax = plt.subplots(figsize=(3.7, 3.3))
    t1 = t[("flat", 1)]["mean_wall_s"] / 60
    xline = np.linspace(1, 5, 100)
    ax.plot(xline, t1 / xline, "--", color="0.5", lw=1.0, zorder=2)
    handles = []
    for arm, colour, label in (("flat", FLAT, "Flat peers"), ("leader", LEADER, "Supervised")):
        ns = sorted(n for (a, n) in t if a == arm)
        ys = [t[(arm, n)]["mean_wall_s"] / 60 for n in ns]
        errs = [_ci(recs, arm, "wall_seconds", n) / 60 for n in ns]
        ax.errorbar(ns, ys, yerr=errs, fmt="none", ecolor="0.45", elinewidth=0.7,
                    capsize=2, capthick=0.7, zorder=3)
        ax.plot(ns, ys, "-", color="black", lw=0.7, zorder=3)
        ax.scatter(ns, ys, s=34, marker="o", zorder=4, linewidths=0.3, edgecolors="black", c=colour)
        for x, y in zip(ns, ys):
            ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(6, -8),
                        ha="left", fontsize=4.5, color="black", fontname="Helvetica")
        handles.append(Line2D([0], [0], color="black", lw=0.7, marker="o", markersize=5,
                              markerfacecolor=colour, markeredgecolor="black", markeredgewidth=0.3, label=label))
    handles.append(Line2D([0], [0], color="0.5", lw=1.0, ls="--", label="Perfect parallelism  $T_1/N$"))
    top = max(t[k]["mean_wall_s"] / 60 for k in t)
    ax.set_ylim(0, top * 1.3)
    _fig2_chrome(fig, ax, [1, 2, 3, 4, 5], "Minutes to completion")
    _fig2_legend(ax, handles, loc="upper left", bbox=(0.03, 0.97))
    return _save(fig, "fig3d_wallclock_topology.png", facecolor="white")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _style()
    recs = load_records()
    print(f"Loaded {len(recs)} runs across {len({r['pool_id'] for r in recs})} pools.")
    print(f"  wrote {figure3a(recs)}")
    print(f"  wrote {figure3b(recs)}")
    print(f"  wrote {figure3c(load_accounts())}")
    print(f"  wrote {figure3d(recs)}")


if __name__ == "__main__":
    main()
