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

import colorsys
import os
import sys

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
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

# (the 95% t table that used to live here went with the CI bars — every figure
#  now draws +/-1 SD across pool means instead; see _sd)


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
# fig2c tints its markers within ONE hue so a series reads as a single colour
# while brightness tracks the value. Same helper, purple instead of the flat
# study's green, so the supervised efficiency figure is instantly separable
# from its sibling. Validated: L in band, chroma above floor, contrast 5.0-6.5
# on white across the range.
LEAD_EFF_HUE = 0.78  # purple — fig3e efficiency markers


def _norm(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo))) if hi > lo else 1.0


def _mono_shade(v, hue, lo, hi):
    t = _norm(v, lo, hi)
    return colorsys.hsv_to_rgb(hue, 0.45 + 0.45 * t, 0.55 + 0.40 * t)


def _bar_colour(colour, darken=0.60, sat_boost=1.15):
    """Error-bar colour derived from the arm whose interval it is.

    fig3b and fig3d overlay both topologies on one axis, and their intervals
    overlap at several team sizes. Drawing every bar in one shared grey ("0.45")
    made it impossible to tell a flat interval from a supervised one; each arm
    now carries bars in its own hue, darkened so a 0.9pt line stays legible.
    """
    h, s, v = colorsys.rgb_to_hsv(*to_rgb(colour))
    return colorsys.hsv_to_rgb(h, min(1.0, s * sat_boost), max(0.0, v * darken))


# Per-arm bar brightness. The supervised red is lifted well above the default
# so it reads as red rather than maroon; the flat teal stays dark because it
# is already the lighter-looking of the two at equal value. Contrast on white
# is 8.2 (leader) and 10.2 (flat), and lifting the red widens their separation
# to dE 89.
BAR_DARKEN = {"flat": 0.60, "leader": 0.92}


# fig2d's four-account ramp, reused verbatim so fig3c reads as its sibling:
# cool = the base work you would pay anyway, warm = the coordination tax.
ACCOUNTS = [("Context", "context", "#cfe6ef"), ("Task", "task", "#1b7ba0"),
            ("Comm", "comm", "#ef8080"), ("Rework", "rework", "#b01e28")]


def _sd(recs, arm, field, agents):
    """+/-1 SD across POOL means — the single construction behind every bar.

    Matches fig2a/2b/2e: average the runs within each pool, then take the plain
    standard deviation across those pool means. This is descriptive spread
    between pools, not a confidence interval, so it makes no inferential claim
    and is not a significance test. The pool is the unit because runs inside one
    share a repo, a task and a feature clique, and because for a binary outcome
    the run-level SD is just sqrt(p(1-p)) — fixed by the rate already plotted.
    """
    from collections import defaultdict
    by_pool = defaultdict(list)
    for r in recs:
        if r["arm"] == arm and r["agents"] == agents and r.get(field) is not None:
            by_pool[r["pool_id"]].append(float(r[field]))
    pool_means = np.array([np.mean(v) for v in by_pool.values()])
    if len(pool_means) < 2:
        return 0.0
    return float(pool_means.std(ddof=1))


def _clip_bars(points, sds, lo=None, hi=None):
    """Split symmetric SD bars into [down, up] distances, clipped to a range."""
    down, up = [], []
    for p, s in zip(points, sds):
        d = s if lo is None else min(s, p - lo)
        u = s if hi is None else min(s, hi - p)
        down.append(max(d, 0.0))
        up.append(max(u, 0.0))
    return [down, up]


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
        # +/-1 SD across pool means, clipped to [0, 1] (matches fig2a)
        errs = [_sd(recs, arm, "all_passed", n) for n in ns]
        # dodge the bars so the two arms' SD bars do not sit on top of each
        # other at the sizes N where both are present (markers stay on true N)
        dx = 0.055 if arm == "leader" else -0.055
        ax.errorbar([n + dx for n in ns], ys, yerr=_clip_bars(ys, errs, 0.0, 1.0), fmt="none",
                    ecolor=_bar_colour(colour, BAR_DARKEN[arm]),
                    elinewidth=0.9, capsize=2.2, capthick=0.9, zorder=3)
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
    sizes = sorted({n for _, n in dec})
    w = 0.38
    # A fine cross-hatch marks the supervised arm. hatch.linewidth is global in
    # matplotlib, so set it here and restore afterwards; 0.25 keeps the mesh
    # readable as a texture without competing with the account fills the way
    # the default-weight diagonal hatch did.
    prev_hlw = plt.rcParams.get("hatch.linewidth", 1.0)
    plt.rcParams["hatch.linewidth"] = 0.12
    fig, ax = plt.subplots(figsize=(4.4, 3.3))
    for off, arm, hatch in ((-w / 2 - 0.02, "flat", None), (w / 2 + 0.02, "leader", "+++++")):
        xs, bottoms = [], {}
        for n in sizes:
            if (arm, n) in dec:
                xs.append(n); bottoms[n] = 0.0
        for _label, key, colour in ACCOUNTS:
            hs = [dec[(arm, n)][key] for n in xs]
            ax.bar([x + off for x in xs], hs, bottom=[bottoms[n] for n in xs], width=w,
                   color=colour, edgecolor="black", linewidth=0.4, zorder=3, hatch=hatch)
            for n, h in zip(xs, hs):
                bottoms[n] += h
        for n in xs:
            tot = dec[(arm, n)]["total"]
            ax.annotate(f"${tot:.2f}", (n + off, tot), textcoords="offset points", xytext=(0, 2),
                        ha="center", va="bottom", fontsize=4.0, color="black", fontname="Helvetica")
            cap = dec[(arm, n)]["comm"] + dec[(arm, n)]["rework"]
            if cap > 0:
                ax.annotate(f"{dec[(arm, n)]['comm_rework_share']*100:.0f}%", (n + off, tot - cap / 2),
                            ha="center", va="center", fontsize=4.2, color="#3d1c0a", fontweight="bold",
                            fontname="Helvetica",
                            bbox=dict(boxstyle="round,pad=0.14", fc="white", ec="none", alpha=0.75))
    ax.set_ylim(0, max(v["total"] for v in dec.values()) * 1.16)
    handles = [Patch(facecolor=c, edgecolor="black", linewidth=0.4, label=lbl) for lbl, _k, c in ACCOUNTS]
    handles += [Patch(facecolor="white", edgecolor="black", linewidth=0.4, label="Flat peers"),
                Patch(facecolor="white", edgecolor="black", linewidth=0.4, hatch="+++++", label="Supervised")]
    _fig2_chrome(fig, ax, sizes, "US dollars")
    _fig2_legend(ax, handles, loc="upper left", bbox=(0.02, 0.98))
    out = _save(fig, "fig3c_accounts_topology.png", facecolor="white")
    plt.rcParams["hatch.linewidth"] = prev_hlw
    return out


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
    bar_top = 0.0  # tallest point+SD, so the ylim below leaves room for the bars
    for arm, colour, label in (("flat", FLAT, "Flat peers"), ("leader", LEADER, "Supervised")):
        ns = sorted(n for (a, n) in t if a == arm)
        ys = [t[(arm, n)]["mean_wall_s"] / 60 for n in ns]
        errs = [_sd(recs, arm, "wall_seconds", n) / 60 for n in ns]
        bar_top = max(bar_top, max(y + e for y, e in zip(ys, errs)))
        dx = 0.055 if arm == "leader" else -0.055
        ax.errorbar([n + dx for n in ns], ys, yerr=_clip_bars(ys, errs, lo=0.0), fmt="none",
                    ecolor=_bar_colour(colour, BAR_DARKEN[arm]),
                    elinewidth=0.9, capsize=2.2, capthick=0.9, zorder=3)
        ax.plot(ns, ys, "-", color="black", lw=0.7, zorder=3)
        ax.scatter(ns, ys, s=34, marker="o", zorder=4, linewidths=0.3, edgecolors="black", c=colour)
        for x, y in zip(ns, ys):
            ax.annotate(f"{y:.1f}", (x, y), textcoords="offset points", xytext=(6, -8),
                        ha="left", fontsize=4.5, color="black", fontname="Helvetica")
        handles.append(Line2D([0], [0], color="black", lw=0.7, marker="o", markersize=5,
                              markerfacecolor=colour, markeredgecolor="black", markeredgewidth=0.3, label=label))
    handles.append(Line2D([0], [0], color="0.5", lw=1.0, ls="--", label="Perfect parallelism  $T_1/N$"))
    ax.set_ylim(0, bar_top * 1.08)
    _fig2_chrome(fig, ax, [1, 2, 3, 4, 5], "Minutes to completion")
    _fig2_legend(ax, handles, loc="upper left", bbox=(0.03, 0.97))
    return _save(fig, "fig3d_wallclock_topology.png", facecolor="white")


# =========================================================================
# FIGURE 3e — efficiency vs team size, SUPERVISED arm alone
# =========================================================================
# The direct counterpart of fig2c (which does this for flat peers, in green):
# linear axes, so the collapse reads as the curve it is rather than the
# straight line log-log turns it into. Purple markers separate it at a glance
# from its flat-study sibling. fig3a keeps the two arms together on log-log,
# where the exponents are slopes and the crossover is visible; this figure is
# the single-arm shape.
def figure3e(recs):
    agg = calc1_aggregate(recs)
    eff = calc2_efficiency(agg)
    pl = calc3_power_law(eff, "leader")
    ns = [n for n, _ in pl["points"]]
    effv = [e for _, e in pl["points"]]
    a, b = pl["a"], pl["b"]

    fig, ax = plt.subplots(figsize=(3.7, 3.3))
    xfit = np.linspace(min(ns), max(ns), 100)
    ax.plot(xfit, a * xfit ** (-b), "--", color="0.45", lw=1.0, zorder=2)
    # one hue (purple); markers fade with the collapse but read as one series
    lo, hi = min(effv), max(effv)
    cvals = [_mono_shade(e, LEAD_EFF_HUE, lo, hi) for e in effv]
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
               markerfacecolor=_mono_shade(hi, LEAD_EFF_HUE, lo, hi),
               markeredgecolor="black", markeredgewidth=0.3,
               label="Efficiency (solved / \\$)"),
    ]
    _fig2_chrome(fig, ax, ns, "Work solved per dollar")
    _fig2_legend(ax, handles)
    return _save(fig, "fig3e_efficiency_supervised.png", facecolor="white")


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _style()
    recs = load_records()
    print(f"Loaded {len(recs)} runs across {len({r['pool_id'] for r in recs})} pools.")
    print(f"  wrote {figure3a(recs)}")
    print(f"  wrote {figure3b(recs)}")
    print(f"  wrote {figure3c(load_accounts())}")
    print(f"  wrote {figure3d(recs)}")
    print(f"  wrote {figure3e(recs)}")


if __name__ == "__main__":
    main()
