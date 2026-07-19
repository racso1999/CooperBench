"""Graded scoring for the shared-git ("agents own the integration") experiment.

In the shared-repo mode, each agent fetches its peers, ``git merge``s their work,
resolves conflicts, and rebuilds its own ``patch.txt`` from the *integrated* tree.
So there is nothing for eval to merge — the integration already happened, on the
agent side (validated at N=2/3/4: every agent merged every peer and produced a
converging integrated patch).

This module therefore does NOT merge anything.  It scores a single **already-
integrated** patch against **all K** feature suites (graded), reusing the core
sandbox primitives (``_run_tests`` / ``_write_patch`` / ``_filter_test_files`` /
``_load_patch``) exactly as ``sandbox.test_solo`` does for two features.  Core eval
is untouched.

Team result: agents converge on ~the same integrated tree, but the team still
*ships one artifact*.  We designate an **integrator** (``agent1`` by default) whose
integrated patch is the team's deliverable, and also score every agent's patch so
divergence is visible (``best_score`` / per-agent).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cooperbench.eval.backends import get_backend
from cooperbench.eval.sandbox import (
    _filter_test_files,
    _load_patch,
    _run_tests,
    _write_patch,
)
from cooperbench.runner.tasks import DEFAULT_DATASET_DIR
from cooperbench.utils import get_image_name


def test_integrated(
    repo_name: str,
    task_id: int,
    feature_ids: list[int],
    patch: str | Path | None,
    *,
    timeout: int = 600,
    backend: str = "docker",
    dataset_dir: str | Path | None = None,
) -> dict:
    """Score ONE integrated patch against all K feature suites (one sandbox, graded).

    Returns ``{k, n_passed, score, all_passed, features: {fid: {...}}, patch_lines,
    error}``.  ``score`` = n_passed / k is the graded performance metric.
    """
    root = Path(dataset_dir) if dataset_dir is not None else DEFAULT_DATASET_DIR
    task_dir = Path(root) / repo_name / f"task{task_id}"

    tests_paths: dict[int, Path] = {}
    for f in feature_ids:
        p = task_dir / f"feature{f}" / "tests.patch"
        if not p.exists():
            return _error(f"Tests patch not found: {p}", feature_ids)
        tests_paths[f] = p

    patch_content = _filter_test_files(_load_patch(patch) or "")

    sb = get_backend(backend).create_sandbox(get_image_name(repo_name, task_id), timeout)
    try:
        base_sha = sb.exec("bash", "-c", "cd /workspace/repo && git rev-parse HEAD").stdout_read().strip()
        if not base_sha:
            return _error("Failed to get base commit SHA", feature_ids)

        _write_patch(sb, "final.patch", patch_content)
        for f in feature_ids:
            _write_patch(sb, f"tests_{f}.patch", tests_paths[f].read_text())

        features: dict[int, dict] = {}
        for f in feature_ids:
            # _run_tests resets to base before applying, so features don't contaminate.
            r = _run_tests(sb, f"tests_{f}.patch", "final.patch", base_sha)
            features[f] = {
                "feature_id": f,
                "passed": r["passed"],
                "tests_passed": r.get("tests_passed", 0),
                "tests_failed": r.get("tests_failed", 0),
            }
        n_passed = sum(1 for f in feature_ids if features[f]["passed"])
        k = len(feature_ids)
        return {
            "k": k,
            "n_passed": n_passed,
            "score": n_passed / k if k else 0.0,
            "all_passed": n_passed == k,
            "features": features,
            "patch_lines": len(patch_content.splitlines()) if patch_content else 0,
            "error": None,
        }
    except Exception as e:  # noqa: BLE001 — surface sandbox errors as a result
        return _error(str(e), feature_ids)
    finally:
        sb.terminate()


def score_team(
    repo_name: str,
    task_id: int,
    feature_ids: list[int],
    agent_patches: dict[str, str | Path | None],
    *,
    integrator: str | None = None,
    timeout: int = 600,
    backend: str = "docker",
    dataset_dir: str | Path | None = None,
) -> dict:
    """Score the team's integrated result on a shared-git run.

    Scores every agent's integrated patch against all K suites.  The **team score**
    is the designated ``integrator``'s (default: the lexicographically first agent,
    i.e. ``agent1``) — the shipped artifact.  ``best_score`` / per-agent are logged
    so integration divergence is visible.  N=1 degenerates to scoring the one agent.
    """
    agent_ids = sorted(agent_patches)
    if integrator is None:
        integrator = agent_ids[0]

    per_agent: dict[str, dict] = {}
    for a in agent_ids:
        per_agent[a] = test_integrated(
            repo_name,
            task_id,
            feature_ids,
            agent_patches[a],
            timeout=timeout,
            backend=backend,
            dataset_dir=dataset_dir,
        )

    team = per_agent[integrator]
    best = max(per_agent.values(), key=lambda r: r.get("n_passed", 0))
    return {
        "repo": repo_name,
        "task_id": task_id,
        "setting": "scaling-git",
        "n_agents": len(agent_ids),
        "feature_ids": list(feature_ids),
        "integrator": integrator,
        # team result = the shipped (integrator's) integrated tree
        "score": team.get("score", 0.0),
        "n_passed": team.get("n_passed", 0),
        "k": team.get("k", len(feature_ids)),
        "all_passed": team.get("all_passed", False),
        "features": team.get("features", {}),
        # robustness: did ANY agent hold a fully-correct integration?
        "best_score": best.get("score", 0.0),
        "best_all_passed": best.get("all_passed", False),
        "per_agent_score": {a: per_agent[a].get("score", 0.0) for a in agent_ids},
        "error": team.get("error"),
        "evaluated_at": datetime.now().isoformat(),
    }


def _error(msg: str, feature_ids: list[int]) -> dict:
    """Uniform error payload with a zero graded score."""
    return {
        "k": len(feature_ids),
        "n_passed": 0,
        "score": 0.0,
        "all_passed": False,
        "features": {f: {"feature_id": f, "passed": False} for f in feature_ids},
        "patch_lines": 0,
        "error": msg,
    }
