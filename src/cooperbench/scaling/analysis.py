"""Analysis outputs for the scaling experiment.

Consumes the flat rows from ``experiment.run_experiment`` (or ``rows.jsonl``) and
produces ``runs.csv`` + ``analysis.json``:

* **Quadratic fits** ``y(N) = alpha*N + beta*N^2`` (no intercept), where ``beta>0``
  (CI strictly above 0) is a superlinear tax.  Three targets, because the effect
  lives in different places:
  - ``cost_fit_comm`` — total dollar cost.  Weak by construction: the ~linear
    per-agent context floor dominates total cost, so total-cost ``beta`` under-
    detects coordination curvature.
  - ``comm_fit`` — the **comm-bucket dollars** (comm condition).  This is where the
    coordination tax actually concentrates, so its ``beta`` is the sharper headline.
  - ``tax_fit`` — ``tax(N) = cost_comm(N) - cost_nocomm(N)`` per pool.  The paired
    difference removes the shared floor, isolating the communication cost directly.
* **cost_curve** — mean ± sd of dollar cost and comm dollars per (N, condition):
  the error-bar curve behind the fits.
* **per_pool_cost_fits** — the cost fit run per pool, then ``beta`` aggregated
  (mean/sd/se) across pools, so pool heterogeneity is not conflated with the
  N-effect of one pooled regression.
* **failure_mix** vs N, and a **driver_regression** of excess (comm+rework) on
  ``{message_reads, conflict_events, rework_turns}``.

Linear algebra is a small pure-Python OLS (no numpy).  CI critical values use an
exact Student-t table for small dof (falling back to scipy if present, then z=1.96
only for large dof) — so small-sample CIs are not understated.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

# Fixed CSV column order (spec columns, then dollar buckets, then audit columns).
RUNS_CSV_FIELDS = [
    "pool_id",
    "repo",
    "task_id",
    "features",
    "K",
    "N",
    "condition",
    "trial",
    "seed",
    "context_tokens",
    "task_tokens",
    "comm_tokens",
    "rework_tokens",
    "buckets_recoverable",
    "context_usd",
    "task_usd",
    "comm_usd",
    "rework_usd",
    "total_tokens",
    "dollar_cost",
    "total_steps",
    "score",
    "n_passed",
    "best_score",
    "git_integrated",
    "all_passed",
    "pass",
    "failure_bucket",
    "merge_status",
    "messages_sent",
    "message_reads",
    "conflict_events",
    "rework_turns",
    "comm_sent_tokens",
    "comm_recv_tokens",
    "comm_reingest_tokens",
]

FAILURE_BUCKETS = ["success", "capability_fail", "merge_conflict", "merged_but_tests_fail"]

# Two-sided 97.5% Student-t quantiles by degrees of freedom (df 1..30).
_T95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


# === tiny linear algebra (pure Python) ======================================


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve ``a x = b`` via Gaussian elimination with partial pivoting (or None)."""
    n = len(b)
    m = [list(row) + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        pv = m[col][col]
        m[col] = [v / pv for v in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0.0:
                factor = m[r][col]
                m[r] = [v - factor * m[col][k] for k, v in enumerate(m[r])]
    return [m[i][n] for i in range(n)]


def _inv2(mat: list[list[float]]) -> list[list[float]] | None:
    """Inverse of a 2×2 matrix, or ``None`` if singular."""
    (a, b), (c, d) = mat
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    return [[d / det, -b / det], [-c / det, a / det]]


def _t_crit(df: int, alpha: float = 0.05) -> tuple[float, str]:
    """Two-sided critical value: scipy-exact if present, else t-table, else z."""
    if df < 1:
        return float("inf"), "undefined-df"
    try:
        from scipy import stats  # type: ignore

        return float(stats.t.ppf(1 - alpha / 2, df)), "t-scipy"
    except Exception:  # noqa: BLE001 — scipy optional
        pass
    if df in _T95:
        return _T95[df], "t-table"
    return 1.96, "z-large-df"  # df > 30: t within ~4% of z


# === IO =====================================================================


def load_rows(rows_or_path: list[dict] | str | Path) -> list[dict]:
    """Accept rows in memory or a path to ``rows.jsonl``."""
    if isinstance(rows_or_path, (str, Path)):
        return [json.loads(ln) for ln in Path(rows_or_path).read_text().splitlines() if ln.strip()]
    return list(rows_or_path)


def write_runs_csv(rows: list[dict], path: str | Path) -> None:
    """Write ``runs.csv`` with the fixed column order."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RUNS_CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RUNS_CSV_FIELDS})


# === quadratic fit core =====================================================


def _fit_quadratic(points: list[tuple[float, float]], label: str) -> dict:
    """Fit ``y = alpha*N + beta*N^2`` (no intercept) to ``(N, y)`` points.

    Shared by the cost / comm / tax fits.  Returns coefficients, SEs, 95% CIs,
    R² (about zero), n, dof, and the critical-value method — or ``{"error": ...}``
    when under-determined.
    """
    pts = [(float(x), float(y)) for x, y in points]
    if len({x for x, _ in pts}) < 2 or len(pts) < 3:
        return {"error": "not enough points / N-levels to fit", "target": label, "n": len(pts)}

    s11 = sum(x * x for x, _ in pts)  # Σ N^2
    s12 = sum(x**3 for x, _ in pts)  # Σ N^3
    s22 = sum(x**4 for x, _ in pts)  # Σ N^4
    t1 = sum(x * y for x, y in pts)  # Σ N y
    t2 = sum(x * x * y for x, y in pts)  # Σ N^2 y

    inv = _inv2([[s11, s12], [s12, s22]])
    if inv is None:
        return {"error": "singular design", "target": label, "n": len(pts)}
    alpha = inv[0][0] * t1 + inv[0][1] * t2
    beta = inv[1][0] * t1 + inv[1][1] * t2

    resid = [y - (alpha * x + beta * x * x) for x, y in pts]
    ss_res = sum(e * e for e in resid)
    ss_tot = sum(y * y for _, y in pts)
    dof = len(pts) - 2
    sigma2 = ss_res / dof if dof > 0 else float("nan")
    se_a = math.sqrt(sigma2 * inv[0][0]) if sigma2 == sigma2 and inv[0][0] > 0 else float("nan")
    se_b = math.sqrt(sigma2 * inv[1][1]) if sigma2 == sigma2 and inv[1][1] > 0 else float("nan")
    tcrit, method = _t_crit(dof)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    def ci(point: float, se: float) -> list[float]:
        if se != se or tcrit == float("inf"):
            return [float("nan"), float("nan")]
        return [point - tcrit * se, point + tcrit * se]

    beta_ci = ci(beta, se_b)
    return {
        "target": label,
        "model": "y(N) = alpha*N + beta*N^2",
        "alpha": alpha,
        "alpha_se": se_a,
        "alpha_ci95": ci(alpha, se_a),
        "beta": beta,
        "beta_se": se_b,
        "beta_ci95": beta_ci,
        "beta_superlinear": bool(beta_ci[0] == beta_ci[0] and beta_ci[0] > 0),
        "r2": r2,
        "n": len(pts),
        "dof": dof,
        "crit_method": method,
    }


def _num(v) -> float | None:
    """Coerce a possibly-blank cell to float, or None."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fit_cost_quadratic(rows: list[dict], condition: str = "comm") -> dict:
    """Total-dollar-cost fit on ``condition`` (dominated by the context floor)."""
    pts = [(float(r["N"]), float(r["dollar_cost"])) for r in rows if r.get("condition") == condition]
    return _fit_quadratic(pts, f"dollar_cost[{condition}]")


def fit_comm_quadratic(rows: list[dict], condition: str = "comm") -> dict:
    """Comm-bucket-dollar fit — where the coordination tax concentrates.

    Falls back to ``comm_tokens`` when dollar buckets are unavailable (unpriced
    model), noting the unit in the target label.
    """
    pts = []
    used_usd = True
    for r in rows:
        if r.get("condition") != condition:
            continue
        y = _num(r.get("comm_usd"))
        if y is None:
            y = _num(r.get("comm_tokens"))
            used_usd = False
        if y is not None:
            pts.append((float(r["N"]), y))
    return _fit_quadratic(pts, f"comm_{'usd' if used_usd else 'tokens'}[{condition}]")


def _tax_points(rows: list[dict], y_key: str = "dollar_cost") -> list[tuple[float, float]]:
    """Per (pool, N): mean(comm y) − mean(nocomm y) — the paired coordination tax."""
    agg: dict[tuple[str, int], dict[str, list[float]]] = defaultdict(lambda: {"comm": [], "nocomm": []})
    for r in rows:
        y = _num(r.get(y_key))
        if y is None:
            continue
        cond = r.get("condition")
        if cond in ("comm", "nocomm"):
            agg[(r["pool_id"], int(r["N"]))][cond].append(y)
    pts = []
    for (_pool, n), d in agg.items():
        if d["comm"] and d["nocomm"]:
            pts.append((float(n), sum(d["comm"]) / len(d["comm"]) - sum(d["nocomm"]) / len(d["nocomm"])))
    return pts


def fit_tax_quadratic(rows: list[dict]) -> dict:
    """Fit ``tax(N) = cost_comm − cost_nocomm`` — floor cancels in the difference."""
    return _fit_quadratic(_tax_points(rows, "dollar_cost"), "tax(dollar_cost)")


def cost_curve(rows: list[dict]) -> dict:
    """Mean ± sd of dollar cost and comm dollars per (N, condition) — error bars."""

    def stat(vals: list[float]) -> dict:
        n = len(vals)
        if n == 0:
            return {"n": 0, "mean": None, "sd": None}
        mu = sum(vals) / n
        sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
        return {"n": n, "mean": mu, "sd": sd}

    by_cell: dict[tuple[int, str], dict[str, list[float]]] = defaultdict(lambda: {"cost": [], "comm": []})
    for r in rows:
        key = (int(r["N"]), r.get("condition", "?"))
        c = _num(r.get("dollar_cost"))
        if c is not None:
            by_cell[key]["cost"].append(c)
        cu = _num(r.get("comm_usd"))
        if cu is not None:
            by_cell[key]["comm"].append(cu)
    out: dict[str, dict] = {}
    for (n, cond), d in sorted(by_cell.items()):
        out[f"N{n}_{cond}"] = {"dollar_cost": stat(d["cost"]), "comm_usd": stat(d["comm"])}
    return out


def performance_curve(rows: list[dict]) -> dict:
    """Graded performance vs N — the headline for the shared-git experiment.

    Per N: mean ± sd of the graded ``score`` (fraction of K features passing on the
    integrated tree) and the strict ``all_passed`` rate, plus mean cost.  This is
    the solo→2→3→4→5 performance curve.
    """
    by_n: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_n[int(r["N"])].append(r)
    out: dict[int, dict] = {}
    for n, group in sorted(by_n.items()):
        scores = [s for r in group if (s := _num(r.get("score"))) is not None]
        costs = [c for r in group if (c := _num(r.get("dollar_cost"))) is not None]
        passed = sum(1 for r in group if r.get("all_passed") in (True, "True"))
        mean = sum(scores) / len(scores) if scores else None
        sd = math.sqrt(sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)) if len(scores) > 1 else 0.0
        out[n] = {
            "n_runs": len(group),
            "mean_score": mean,
            "sd_score": sd if mean is not None else None,
            "all_passed_rate": passed / len(group) if group else None,
            "mean_cost": sum(costs) / len(costs) if costs else None,
        }
    return out


def per_pool_cost_fits(rows: list[dict]) -> dict:
    """Cost fit per pool, then ``beta`` aggregated across pools (mean/sd/se)."""
    by_pool: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_pool[r["pool_id"]].append(r)
    fits = {pool: fit_cost_quadratic(rs, "comm") for pool, rs in by_pool.items()}
    betas = [f["beta"] for f in fits.values() if "beta" in f and f["beta"] == f["beta"]]
    agg: dict = {"n_pools_fit": len(betas)}
    if betas:
        mu = sum(betas) / len(betas)
        sd = math.sqrt(sum((b - mu) ** 2 for b in betas) / (len(betas) - 1)) if len(betas) > 1 else 0.0
        agg.update({"beta_mean": mu, "beta_sd": sd, "beta_se": sd / math.sqrt(len(betas)) if betas else None})
    return {"per_pool": fits, "aggregate_beta": agg}


def failure_mix(rows: list[dict]) -> dict:
    """Share of each failure bucket at each N (comm + nocomm pooled and split)."""

    def mix(subset: list[dict]) -> dict:
        out: dict[int, dict] = {}
        by_n: dict[int, list[dict]] = defaultdict(list)
        for r in subset:
            by_n[int(r["N"])].append(r)
        for n, group in sorted(by_n.items()):
            counts = {b: 0 for b in FAILURE_BUCKETS}
            for r in group:
                b = r.get("failure_bucket")
                if b in counts:
                    counts[b] += 1
            total = max(len(group), 1)
            out[n] = {"n_runs": len(group), **{b: counts[b] / total for b in FAILURE_BUCKETS}}
        return out

    return {
        "all": mix(rows),
        "comm": mix([r for r in rows if r.get("condition") == "comm"]),
        "nocomm": mix([r for r in rows if r.get("condition") == "nocomm"]),
    }


def _standardize(col: list[float]) -> list[float]:
    """Zero-mean, unit-sd standardization (sd=0 ⇒ centered zeros)."""
    n = len(col)
    mu = sum(col) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in col) / n)
    if sd == 0:
        return [0.0 for _ in col]
    return [(x - mu) / sd for x in col]


def driver_regression(rows: list[dict]) -> dict:
    """Regress per-run excess (comm+rework) tokens on the coordination drivers."""
    driver_names = ["message_reads", "conflict_events", "rework_turns"]

    def fit(subset: list[dict]) -> dict:
        usable = [r for r in subset if r.get("buckets_recoverable")]
        if len(usable) < len(driver_names) + 2:
            return {"error": "not enough recoverable rows", "n": len(usable)}
        y_raw = [float(r.get("comm_tokens") or 0) + float(r.get("rework_tokens") or 0) for r in usable]
        cols = [[float(r.get(d) or 0) for r in usable] for d in driver_names]
        yz = _standardize(y_raw)
        xz = [_standardize(c) for c in cols]
        p = len(driver_names) + 1
        design = [[1.0] + [xz[j][i] for j in range(len(driver_names))] for i in range(len(usable))]
        xtx = [[sum(design[r][i] * design[r][j] for r in range(len(usable))) for j in range(p)] for i in range(p)]
        xty = [sum(design[r][i] * yz[r] for r in range(len(usable))) for i in range(p)]
        coef = _solve(xtx, xty)
        if coef is None:
            return {"error": "singular design", "n": len(usable)}
        std_betas = {d: coef[i + 1] for i, d in enumerate(driver_names)}
        dominant = max(std_betas, key=lambda k: abs(std_betas[k]))
        return {"n": len(usable), "std_coefficients": std_betas, "dominant": dominant}

    per_n: dict[int, dict] = {}
    by_n: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_n[int(r["N"])].append(r)
    for n, group in sorted(by_n.items()):
        per_n[n] = fit(group)

    overall = fit(rows)
    doms = {n: v.get("dominant") for n, v in per_n.items() if "dominant" in v}
    shifts = len(set(doms.values())) > 1 if doms else None
    return {"overall": overall, "per_N": per_n, "dominant_by_N": doms, "shifts_with_N": shifts}


def run_analysis(rows_or_path: list[dict] | str | Path, out_dir: str | Path) -> dict:
    """Write ``runs.csv`` + ``analysis.json`` and return the analysis dict."""
    rows = load_rows(rows_or_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_runs_csv(rows, out / "runs.csv")

    analysis = {
        "n_runs": len(rows),
        "performance_curve": performance_curve(rows),
        "cost_fit_comm": fit_cost_quadratic(rows, "comm"),
        "cost_fit_nocomm": fit_cost_quadratic(rows, "nocomm"),
        "comm_fit": fit_comm_quadratic(rows, "comm"),
        "tax_fit": fit_tax_quadratic(rows),
        "cost_curve": cost_curve(rows),
        "per_pool_cost_fits": per_pool_cost_fits(rows),
        "failure_mix": failure_mix(rows),
        "driver_regression": driver_regression(rows),
    }
    (out / "analysis.json").write_text(json.dumps(analysis, indent=2, default=str))
    return analysis
