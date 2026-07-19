"""Feature *pools* for the scaling experiment.

A **pool** is ``(repo, task_id, (f1..fK))`` — a K-feature subset of a single
task whose features are *mutually interdependent* so that splitting them across
agents actually exercises coordination.  Pools are derived from the precomputed
pairwise gold-conflict graph (``dataset/gold_conflict_report.json``); no new
gold merges are computed here.

Interdependence has two selectable strengths:

* ``clique``    — all C(K,2) pairs gold-conflict (the induced subgraph is
  complete).  Maximal-signal: every partition boundary is a real conflict site.
  This is the default.
* ``connected`` — the induced conflict subgraph is connected (each feature
  conflicts with >= 1 other).  A documented relaxation for when K-cliques are
  scarce at large K.

Solo-achievability (does a single agent finish all K?) is a *separate* screening
step handled by ``experiment.py`` — it needs to run agents, not just read the
graph.  This module is pure graph/manifest logic and has no side effects beyond
file IO in the explicit read/write helpers.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

from cooperbench.runner.tasks import DEFAULT_DATASET_DIR

# Task key as used in gold_conflict_report.json "per_task": "<repo>/task<ID>".
TaskKey = tuple[str, int]
# Adjacency: feature id -> set of feature ids it gold-conflicts with.
Adjacency = dict[int, set[int]]

REQUIRE_CLIQUE = "clique"
REQUIRE_CONNECTED = "connected"


@dataclass(frozen=True)
class Pool:
    """A validated K-feature pool within one task."""

    repo: str
    task_id: int
    features: tuple[int, ...]
    require: str = REQUIRE_CLIQUE
    # Filled in by screening (experiment.py); None until screened.
    screen: dict = field(default_factory=dict, compare=False)

    @property
    def k(self) -> int:
        return len(self.features)

    @property
    def pool_id(self) -> str:
        """Stable, filesystem-safe identifier used by ``--pool``."""
        feats = "_".join(f"f{f}" for f in self.features)
        return f"{self.repo}/task{self.task_id}/{feats}"


def load_conflict_graph(
    report_path: str | Path | None = None,
    dataset_dir: str | Path | None = None,
) -> dict[TaskKey, Adjacency]:
    """Build a per-task conflict graph from the gold conflict report.

    Edge (f1, f2) exists iff that pair is listed in ``conflict_pairs`` (i.e. the
    two gold ``feature.patch``es produce a git merge conflict).  Returns a mapping
    ``(repo, task_id) -> {feature: {neighbours}}``.
    """
    if report_path is None:
        root = Path(dataset_dir) if dataset_dir is not None else DEFAULT_DATASET_DIR
        report_path = Path(root) / "gold_conflict_report.json"
    report = json.loads(Path(report_path).read_text())

    graph: dict[TaskKey, Adjacency] = {}
    for entry in report.get("conflict_pairs", []):
        key: TaskKey = (entry["repo"], int(entry["task_id"]))
        f1, f2 = int(entry["f1"]), int(entry["f2"])
        adj = graph.setdefault(key, {})
        adj.setdefault(f1, set()).add(f2)
        adj.setdefault(f2, set()).add(f1)
    return graph


def _is_clique(adj: Adjacency, subset: tuple[int, ...]) -> bool:
    """True iff every pair in ``subset`` is an edge."""
    return all(b in adj.get(a, ()) for a, b in combinations(subset, 2))


def _is_connected(adj: Adjacency, subset: tuple[int, ...]) -> bool:
    """True iff the subgraph induced on ``subset`` is connected."""
    members = set(subset)
    if len(members) <= 1:
        return True
    start = subset[0]
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for nb in adj.get(node, ()):  # only neighbours inside the subset count
            if nb in members and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return seen == members


def _qualifies(adj: Adjacency, subset: tuple[int, ...], require: str) -> bool:
    if require == REQUIRE_CLIQUE:
        return _is_clique(adj, subset)
    if require == REQUIRE_CONNECTED:
        return _is_connected(adj, subset)
    raise ValueError(f"unknown require {require!r}; use {REQUIRE_CLIQUE!r} or {REQUIRE_CONNECTED!r}")


def enumerate_pools(
    adj: Adjacency,
    k: int,
    require: str = REQUIRE_CLIQUE,
) -> Iterator[tuple[int, ...]]:
    """Yield every qualifying K-subset of a task's features, in sorted order.

    Subsets are yielded lexicographically (``combinations`` over sorted feature
    ids), so downstream deterministic selection is just "take the first".
    """
    feats = sorted(adj)
    for subset in combinations(feats, k):
        if _qualifies(adj, subset, require):
            yield subset


def select_pool(
    adj: Adjacency,
    k: int,
    require: str = REQUIRE_CLIQUE,
) -> tuple[int, ...] | None:
    """Deterministically pick one qualifying K-subset (lexicographically first)."""
    return next(enumerate_pools(adj, k, require), None)


def largest_supported_k(
    adj: Adjacency,
    kmax: int,
    require: str = REQUIRE_CLIQUE,
) -> int:
    """Largest K in ``2..kmax`` for which this task has a qualifying subset (0 if none)."""
    for k in range(min(kmax, len(adj)), 1, -1):
        if select_pool(adj, k, require) is not None:
            return k
    return 0


def find_candidate_pools(
    k: int,
    tasks: set[TaskKey] | None = None,
    require: str = REQUIRE_CLIQUE,
    report_path: str | Path | None = None,
    dataset_dir: str | Path | None = None,
) -> list[Pool]:
    """One deterministic candidate pool per eligible task.

    ``tasks`` restricts consideration to those ``(repo, task_id)`` keys (e.g. the
    tasks of a subset like flash); ``None`` considers every task in the report.
    Tasks with no qualifying K-subset are skipped.  Result is sorted by task key
    for stable ordering.
    """
    graph = load_conflict_graph(report_path, dataset_dir)
    pools: list[Pool] = []
    for key in sorted(graph):
        if tasks is not None and key not in tasks:
            continue
        subset = select_pool(graph[key], k, require)
        if subset is not None:
            repo, task_id = key
            pools.append(Pool(repo=repo, task_id=task_id, features=subset, require=require))
    return pools


# === Manifest IO (subsets-style JSON) ===================================


def write_manifest(path: str | Path, pools: list[Pool], meta: Mapping | None = None) -> None:
    """Write a pools manifest (subset-file-shaped) to ``path``."""
    payload = {
        "name": Path(path).stem,
        "description": "scaling-experiment pools (conflict-clique subsets, solo-screened)",
        "meta": dict(meta or {}),
        "stats": {"pools": len(pools)},
        "pools": [
            {
                "repo": p.repo,
                "task_id": p.task_id,
                "features": list(p.features),
                "k": p.k,
                "require": p.require,
                "pool_id": p.pool_id,
                "screen": p.screen,
            }
            for p in pools
        ],
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2))


def load_manifest(path: str | Path) -> list[Pool]:
    """Load pools from a manifest written by :func:`write_manifest`."""
    payload = json.loads(Path(path).read_text())
    pools: list[Pool] = []
    for entry in payload.get("pools", []):
        pools.append(
            Pool(
                repo=entry["repo"],
                task_id=int(entry["task_id"]),
                features=tuple(entry["features"]),
                require=entry.get("require", REQUIRE_CLIQUE),
                screen=entry.get("screen", {}),
            )
        )
    return pools


def find_pool_by_id(pool_id: str, pools: list[Pool]) -> Pool | None:
    """Look a pool up by its :attr:`Pool.pool_id`."""
    return next((p for p in pools if p.pool_id == pool_id), None)
