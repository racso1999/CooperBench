"""N-way merge + test evaluation for the scaling experiment.

Generalizes the core two-patch eval (``sandbox.test_merged``) to N agents while
**reusing the core sandbox primitives unchanged** (``_setup``/``_write_patch``/
``_run_tests``/``_filter_test_files``/``_load_patch``).  The core eval is not
modified — this is a separate, additive N-way path.

Merge model (documented, pinned, order-sensitive):

* N branches are created off the base commit, one per agent, each with that
  agent's (test-file-stripped) patch applied.
* They are folded **sequentially in ascending agent-id order**: ``agent1`` is the
  base, then ``git merge agent2 --no-commit --no-ff``, then ``agent3`` … ``agentN``.
  A conflict at *any* fold step marks the whole run ``conflicts`` (the fold aborts;
  there is no lead-alone fallback — that would confound the clean-merge endpoint
  the scaling experiment measures).
* N=1 is the degenerate case: one branch, zero merges; the "merged" tree is just
  that agent's tree.

The merged tree is tested against the held-out ``tests.patch`` of **every** one of
the K features (``all_passed`` generalizes ``both_passed``).  Test-run and
test-file-stripping semantics are inherited verbatim from the core sandbox.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cooperbench.eval.backends import get_backend
from cooperbench.eval.sandbox import (
    _filter_test_files,
    _load_patch,
    _parse_results,
    _run_tests,
    _write_patch,
)
from cooperbench.runner.tasks import DEFAULT_DATASET_DIR
from cooperbench.utils import get_image_name

# Failure taxonomy (one label per run).  Priority order is capability -> merge ->
# tests: an agent that never solved its own feature can't be charged a
# coordination cost, so capability_fail dominates.
BUCKET_SUCCESS = "success"
BUCKET_CAPABILITY = "capability_fail"
BUCKET_CONFLICT = "merge_conflict"
BUCKET_TESTS = "merged_but_tests_fail"


def test_merged_nway(
    repo_name: str,
    task_id: int,
    assignment: dict[str, list[int]],
    patches: dict[str, str | Path | None],
    *,
    timeout: int = 600,
    backend: str = "docker",
    dataset_dir: str | Path | None = None,
    run_independent: bool = True,
) -> dict:
    """Evaluate an N-agent partitioned run.

    Args:
        assignment: agent_id -> list of feature ids that agent owns.  The union
            over all agents is the K-feature workload.  Agent ids are folded in
            sorted order (``agent1`` before ``agent2`` …).
        patches: agent_id -> that agent's patch (str content or path).

    Returns a dict with ``merge`` (status/strategy/fold_order/diff), ``features``
    (per-feature merged-tree result), ``features_independent`` (per-feature
    pre-merge capability), ``all_passed``, ``failure_bucket``, and ``error``.
    """
    root = Path(dataset_dir) if dataset_dir is not None else DEFAULT_DATASET_DIR
    task_dir = Path(root) / repo_name / f"task{task_id}"

    agent_ids = sorted(assignment)  # pinned fold order
    all_features = [f for a in agent_ids for f in assignment[a]]
    feature_owner = {f: a for a in agent_ids for f in assignment[a]}

    # Locate every feature's held-out test suite up front.
    tests_paths: dict[int, Path] = {}
    for f in all_features:
        p = task_dir / f"feature{f}" / "tests.patch"
        if not p.exists():
            return _error_result(f"Tests patch not found: {p}", agent_ids, all_features)
        tests_paths[f] = p

    # Load + strip agent patches.
    patch_content: dict[str, str] = {}
    for a in agent_ids:
        patch_content[a] = _filter_test_files(_load_patch(patches.get(a)) or "")

    image = get_image_name(repo_name, task_id)
    sb = get_backend(backend).create_sandbox(image, timeout)
    try:
        # Write every agent patch + every feature test patch into the sandbox.
        for a in agent_ids:
            _write_patch(sb, f"{a}.patch", patch_content[a])
        for f in all_features:
            _write_patch(sb, f"tests_{f}.patch", tests_paths[f].read_text())

        setup = _setup_branches_nway(sb, agent_ids)
        if setup.get("error"):
            return _error_result(setup["error"], agent_ids, all_features)
        base_sha = setup["base_sha"]
        apply_status = setup["apply_status"]
        any_apply_failed = "failed" in apply_status.values()

        # Pre-merge capability: each feature's own suite vs its owner's patch alone.
        features_independent: dict[int, dict] = {}
        if run_independent:
            for f in all_features:
                owner = feature_owner[f]
                if not patch_content[owner]:
                    features_independent[f] = {
                        "passed": False,
                        "tests_passed": 0,
                        "tests_failed": 0,
                        "reason": "no_patch",
                    }
                    continue
                r = _run_tests(sb, f"tests_{f}.patch", f"{owner}.patch", base_sha)
                features_independent[f] = {
                    "passed": r["passed"],
                    "tests_passed": r.get("tests_passed", 0),
                    "tests_failed": r.get("tests_failed", 0),
                    "reason": None,
                }

        # Fold the branches.
        fold = _merge_fold_nway(sb, base_sha, agent_ids)
        if any_apply_failed:
            merge_status = "missing_input"
        elif fold["conflict"]:
            merge_status = "conflicts"
        else:
            merge_status = "clean"

        # Merged-tree tests: authoritative for a clean merge only.
        features_result: dict[int, dict] = {}
        if merge_status == "clean":
            for f in all_features:
                r = _run_tests(sb, f"tests_{f}.patch", "merged.patch", base_sha)
                features_result[f] = {
                    "feature_id": f,
                    "owner": feature_owner[f],
                    "passed": r["passed"],
                    "exit_code": r.get("exit_code"),
                    "tests_passed": r.get("tests_passed", 0),
                    "tests_failed": r.get("tests_failed", 0),
                }
        else:
            for f in all_features:
                features_result[f] = {
                    "feature_id": f,
                    "owner": feature_owner[f],
                    "passed": False,
                    "exit_code": None,
                    "tests_passed": 0,
                    "tests_failed": 0,
                }

        all_passed = merge_status == "clean" and all(features_result[f]["passed"] for f in all_features)
        bucket = _classify(merge_status, all_passed, features_independent, all_features, run_independent)

        return {
            "repo": repo_name,
            "task_id": task_id,
            "setting": "scaling",
            "n_agents": len(agent_ids),
            "features": [features_result[f] for f in all_features],
            "features_independent": (
                [{"feature_id": f, **features_independent[f]} for f in all_features] if run_independent else None
            ),
            "apply_status": apply_status,
            "merge": {
                "status": merge_status,
                "strategy": "naive-fold",
                "fold_order": agent_ids,
                "diff": (fold.get("diff") or "")[:5000],
            },
            "all_passed": all_passed,
            "failure_bucket": bucket,
            "error": None,
            "evaluated_at": datetime.now().isoformat(),
        }
    except Exception as e:  # noqa: BLE001 — surface any sandbox error as a result
        return _error_result(str(e), agent_ids, all_features)
    finally:
        sb.terminate()


def _classify(
    merge_status: str,
    all_passed: bool,
    independent: dict[int, dict],
    features: list[int],
    run_independent: bool,
) -> str:
    """One failure label per run (see module docstring for priority)."""
    if all_passed:
        return BUCKET_SUCCESS
    # capability dominates: an agent that never solved its own feature (or whose
    # patch failed to apply) is not a coordination failure.
    if run_independent and independent:
        if any(not independent[f]["passed"] for f in features):
            return BUCKET_CAPABILITY
    if merge_status in ("conflicts", "missing_input"):
        return BUCKET_CONFLICT
    return BUCKET_TESTS


def _setup_branches_nway(sb, agent_ids: list[str]) -> dict:
    """Create one branch per agent off the base commit and apply its patch.

    Mirrors ``sandbox._setup_branches`` but for N agents.  Returns ``base_sha``
    and per-agent ``apply_status`` (applied / skipped / failed).
    """
    lines = [
        "cd /workspace/repo",
        'git config user.email "eval@cooperbench.local"',
        'git config user.name "CooperBench Eval"',
        "BASE_SHA=$(git rev-parse HEAD)",
        'echo "BASE_SHA=$BASE_SHA"',
        # apply_patch <name>: plain apply, then --3way fallback.
        "apply_patch() {",
        "  local name=$1",
        "  if [ -s /patches/${name}.patch ]; then",
        '    if git apply /patches/${name}.patch 2>&1; then echo "${name}_APPLIED";',
        '    elif git apply --3way /patches/${name}.patch 2>&1; then echo "${name}_APPLIED";',
        '    else echo "${name}_FAILED"; fi',
        '  else echo "${name}_SKIPPED"; fi',
        "}",
    ]
    for a in agent_ids:
        lines += [
            "git checkout $BASE_SHA 2>&1",
            f"git checkout -b {a} 2>&1",
            f"apply_patch {a}",
            "git add -A",
            f'git commit -m "{a} changes" --allow-empty 2>&1',
        ]
    lines.append('echo "SETUP_COMPLETE"')
    result = sb.exec("bash", "-c", "\n".join(lines))
    output = result.stdout_read() + result.stderr_read()

    if "SETUP_COMPLETE" not in output:
        return {"error": f"Branch setup failed: {output}"}

    base_sha = None
    for line in output.split("\n"):
        if line.startswith("BASE_SHA="):
            base_sha = line.split("=", 1)[1].strip()
            break
    if not base_sha:
        return {"error": "Failed to get base commit SHA"}

    def status(a: str) -> str:
        if f"{a}_APPLIED" in output:
            return "applied"
        if f"{a}_SKIPPED" in output:
            return "skipped"
        return "failed"

    return {"base_sha": base_sha, "apply_status": {a: status(a) for a in agent_ids}, "output": output}


def _merge_fold_nway(sb, base_sha: str, agent_ids: list[str]) -> dict:
    """Sequentially fold ``agent2..agentN`` into ``agent1``; stop at first conflict.

    On a clean fold, writes the base..HEAD diff to ``/patches/merged.patch``.
    """
    base = agent_ids[0]
    rest = agent_ids[1:]
    lines = [
        "cd /workspace/repo",
        f"git checkout {base} 2>&1",
        "CONFLICT=0",
    ]
    for a in rest:
        lines += [
            "if [ $CONFLICT -eq 0 ]; then",
            f"  if git merge {a} --no-commit --no-ff 2>&1; then",
            f'    git commit -m "fold {a}" 2>&1;',
            "  else",
            '    echo "MERGE_STATUS=conflicts";',
            "    git merge --abort 2>/dev/null || true;",
            "    CONFLICT=1;",
            "  fi",
            "fi",
        ]
    lines += [
        "if [ $CONFLICT -eq 0 ]; then",
        '  echo "MERGE_STATUS=clean";',
        f"  git diff {base_sha} HEAD > /patches/merged.patch;",
        "fi",
    ]
    result = sb.exec("bash", "-c", "\n".join(lines))
    output = result.stdout_read() + result.stderr_read()
    conflict = "MERGE_STATUS=conflicts" in output

    diff = ""
    if not conflict:
        diff = sb.exec("cat", "/patches/merged.patch").stdout_read()
    return {"conflict": conflict, "diff": diff, "output": output}


def _error_result(msg: str, agent_ids: list[str], features: list[int]) -> dict:
    """Uniform error payload so callers always get the same shape."""
    return {
        "setting": "scaling",
        "n_agents": len(agent_ids),
        "features": [{"feature_id": f, "passed": False} for f in features],
        "features_independent": None,
        "apply_status": {a: "unknown" for a in agent_ids},
        "merge": {"status": "error", "strategy": None, "fold_order": agent_ids, "diff": ""},
        "all_passed": False,
        "failure_bucket": BUCKET_CONFLICT,
        "error": msg,
        "evaluated_at": datetime.now().isoformat(),
    }


# Re-export so callers importing from this module get the parser too, without
# reaching into sandbox internals.
__all__ = ["test_merged_nway", "_parse_results"]
