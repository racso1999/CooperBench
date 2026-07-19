"""Smoke + unit tests for the scaling experiment.

The end-to-end cell (agent run + N-way sandbox eval) needs Docker and billed API
calls, so ``test_experiment_end_to_end_smoke`` monkeypatches those two expensive
boundaries and exercises the full orchestration → analysis wiring: one pool, K=2,
N∈{1,2}, r=1, both conditions, asserting ``runs.csv`` populates and the fit runs.
The deterministic pieces (partition, pool cliques, bucket parsing, fits) are tested
directly.
"""

from __future__ import annotations

import json

import pytest

from cooperbench.scaling import analysis, buckets, experiment, partition, pools

# --- partition ---------------------------------------------------------------


def test_round_robin_is_deterministic_and_stable_across_n():
    # sorted → [3,6,7,10]; round-robin deal
    assert partition.partition_features([7, 3, 10, 6], 2) == {"agent1": [3, 7], "agent2": [6, 10]}
    assert partition.partition_features([7, 3, 10, 6], 1) == {"agent1": [3, 6, 7, 10]}
    assert partition.partition_features([7, 3, 10, 6], 4) == {
        "agent1": [3],
        "agent2": [6],
        "agent3": [7],
        "agent4": [10],
    }
    # same inputs → same output
    assert partition.partition_features([3, 6, 7, 10], 3) == partition.partition_features([10, 7, 6, 3], 3)


def test_partition_rejects_more_agents_than_features():
    with pytest.raises(ValueError):
        partition.partition_features([1, 2], 3)


# --- pools / cliques ---------------------------------------------------------


def _triangle_plus_pendant() -> pools.Adjacency:
    # 1-2-3 form a triangle (all conflict); 4 conflicts only with 1.
    return {1: {2, 3, 4}, 2: {1, 3}, 3: {1, 2}, 4: {1}}


def test_clique_selection_and_largest_k():
    adj = _triangle_plus_pendant()
    assert pools.select_pool(adj, 3, pools.REQUIRE_CLIQUE) == (1, 2, 3)
    assert pools.select_pool(adj, 4, pools.REQUIRE_CLIQUE) is None  # no 4-clique
    assert pools.largest_supported_k(adj, 4, pools.REQUIRE_CLIQUE) == 3
    # connected relaxation admits the pendant edge into a K=2 subset
    assert pools.select_pool(adj, 2, pools.REQUIRE_CONNECTED) == (1, 2)


def test_manifest_roundtrip(tmp_path):
    p = pools.Pool("some_repo", 7, (1, 2, 3), screen={"passes": 3, "trials": 3})
    path = tmp_path / "pools.json"
    pools.write_manifest(path, [p], meta={"features": 3})
    loaded = pools.load_manifest(path)
    assert len(loaded) == 1
    assert loaded[0].pool_id == p.pool_id == "some_repo/task7/f1_f2_f3"
    assert loaded[0].features == (1, 2, 3)
    assert pools.find_pool_by_id(p.pool_id, loaded) is not None


# --- buckets -----------------------------------------------------------------


def _write_synthetic_stream(log_dir, agent_id):
    """A 3-turn stream: context floor, a coop-recv + first edit, then a re-edit."""

    def assistant(mid, out, cread, content):
        return {
            "type": "assistant",
            "message": {
                "id": mid,
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": out,
                    "cache_read_input_tokens": cread,
                    "cache_creation_input_tokens": 0,
                },
                "content": content,
            },
        }

    events = [
        assistant("m0", 5, 30000, [{"type": "text", "text": "reading"}]),
        assistant(
            "m1",
            20,
            31000,
            [
                {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "coop-recv"}},
                {"type": "tool_use", "id": "e1", "name": "Edit", "input": {"file_path": "a.py"}},
            ],
        ),
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "b1", "content": "[Message from agent2]: touching a.py"}
                ]
            },
        },
        assistant(
            "m2",
            15,
            31500,
            [
                {"type": "tool_use", "id": "e2", "name": "Edit", "input": {"file_path": "a.py"}},
            ],
        ),
        {"type": "result", "total_cost_usd": 0.12, "num_turns": 3, "usage": {"output_tokens": 40}},
    ]
    (log_dir / f"{agent_id}_stream.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    (log_dir / f"{agent_id}_sent.jsonl").write_text(
        json.dumps({"from": agent_id, "to": "agent2", "content": "type: CLAIM\nfiles: a.py"}) + "\n"
    )


def test_buckets_extract_comm_context_and_rework(tmp_path):
    _write_synthetic_stream(tmp_path, "agent1")
    ab = buckets.compute_agent_buckets(tmp_path, "agent1")
    assert ab is not None
    assert ab.n_turns == 3
    assert ab.context_tokens > 0  # resident floor at turn 0
    assert ab.comm_recv_tokens > 0  # received payload counted
    assert ab.comm_sent_tokens > 0  # from the send-log
    assert ab.n_reedits_after_recv >= 1  # re-edit of a.py after inbound message
    run = buckets.compute_run_buckets(tmp_path, ["agent1"])
    assert run["recoverable"] is True
    assert run["run_total"]["comm_tokens"] > 0


def test_buckets_unrecoverable_when_no_stream(tmp_path):
    run = buckets.compute_run_buckets(tmp_path, ["agent1", "agent2"])
    assert run["recoverable"] is False


# --- analysis ----------------------------------------------------------------


def _synthetic_rows():
    # cost(N) ≈ 1*N + 0.5*N^2 (superlinear) on comm; linear-ish on nocomm.
    rows = []
    for n in (1, 2, 3, 4):
        for trial in (1, 2):
            rows.append(
                {
                    "pool_id": "r/task0/f1_f2",
                    "repo": "r",
                    "task_id": 0,
                    "features": "1_2",
                    "K": 4,
                    "N": n,
                    "condition": "comm",
                    "trial": trial,
                    "seed": 0,
                    "context_tokens": 1000,
                    "task_tokens": 500 * n,
                    "comm_tokens": 100 * n * n,
                    "rework_tokens": 10 * n,
                    "buckets_recoverable": True,
                    "total_tokens": 2000 * n,
                    "dollar_cost": 1.0 * n + 0.5 * n * n,
                    "total_steps": 5 * n,
                    "all_passed": n <= 2,
                    "pass": n <= 2,
                    "failure_bucket": "success" if n <= 2 else "merge_conflict",
                    "merge_status": "clean" if n <= 2 else "conflicts",
                    "messages_sent": 2 * n,
                    "message_reads": 3 * n,
                    "conflict_events": 0 if n <= 2 else 1,
                    "rework_turns": n,
                    "comm_sent_tokens": 50 * n,
                    "comm_recv_tokens": 40 * n,
                    "comm_reingest_tokens": 10 * n * n,
                }
            )
    return rows


def test_cost_fit_recovers_positive_beta():
    fit = analysis.fit_cost_quadratic(_synthetic_rows(), "comm")
    assert "beta" in fit
    assert fit["beta"] == pytest.approx(0.5, abs=1e-6)
    assert fit["alpha"] == pytest.approx(1.0, abs=1e-6)
    assert fit["beta_superlinear"] is True


def test_failure_mix_and_driver_regression():
    rows = _synthetic_rows()
    mix = analysis.failure_mix(rows)
    assert mix["comm"][4]["merge_conflict"] == pytest.approx(1.0)
    assert mix["comm"][1]["success"] == pytest.approx(1.0)
    drv = analysis.driver_regression(rows)
    assert "overall" in drv and "per_N" in drv


def test_runs_csv_written(tmp_path):
    analysis.write_runs_csv(_synthetic_rows(), tmp_path / "runs.csv")
    text = (tmp_path / "runs.csv").read_text()
    assert "pool_id,repo,task_id" in text.splitlines()[0]
    assert len(text.splitlines()) == 1 + 8  # header + 8 rows


# --- end-to-end orchestration smoke (mocked run + eval) ----------------------


def test_experiment_end_to_end_smoke(tmp_path, monkeypatch):
    """One pool, K=2, N∈{1,2}, r=1, both conditions — full pipeline, mocked I/O."""
    pool = pools.Pool("openai_tiktoken_task", 0, (2, 3))

    def fake_execute_partitioned(repo_name, task_id, assignment, run_name, **kw):
        n = len(assignment)
        leaf = tmp_path / "logs" / run_name / f"N{n}_{kw['condition']}_r{kw['trial']}"
        leaf.mkdir(parents=True, exist_ok=True)
        for a in assignment:
            (leaf / f"{a}.patch").write_text("")
        result_data = {
            "log_dir": str(leaf),
            "total_cost": 1.0 * n + 0.5 * n * n,
            "total_steps": 4 * n,
            "messages_sent": 2 if kw["condition"] == "comm" else 0,
        }
        return {"result_data": result_data, "log_dir": str(leaf)}

    def fake_test_merged_nway(repo_name, task_id, assignment, patches, **kw):
        return {
            "all_passed": True,
            "failure_bucket": "success",
            "merge": {"status": "clean", "fold_order": sorted(assignment)},
        }

    def fake_compute_run_buckets(log_dir, agent_ids):
        n = len(agent_ids)
        return {
            "recoverable": True,
            "run_total": {
                "context_tokens": 1000,
                "task_tokens": 500 * n,
                "comm_tokens": 100 * n * n,
                "rework_tokens": 10 * n,
                "total_output": 100 * n,
                "total_input": 5,
                "total_cache_read": 2000 * n,
                "total_cache_write": 50,
                "n_sends": n,
                "n_recvs": n,
                "n_messages_read": 3 * n,
                "n_reedits_after_recv": n,
                "comm_sent_tokens": 50 * n,
                "comm_recv_tokens": 40 * n,
                "comm_reingest_tokens": 10 * n * n,
            },
        }

    monkeypatch.setattr(experiment, "execute_partitioned", fake_execute_partitioned)
    monkeypatch.setattr(experiment, "test_merged_nway", fake_test_merged_nway)
    monkeypatch.setattr(experiment, "compute_run_buckets", fake_compute_run_buckets)

    out = tmp_path / "results"
    rows = experiment.run_experiment(
        [pool],
        agents=[1, 2],
        conditions=("comm", "nocomm"),
        trials=1,
        logs_dir=str(tmp_path / "logs"),
        out_dir=str(out),
    )
    # N=1 has only the nocomm cell; N=2 has comm + nocomm → 3 cells.
    assert len(rows) == 3
    assert (out / "rows.jsonl").exists()

    result = analysis.run_analysis(rows, out)
    assert (out / "runs.csv").exists()
    assert (out / "analysis.json").exists()
    assert result["n_runs"] == 3
    # the fits run end-to-end (structured results even if under-determined)
    assert "cost_fit_comm" in result and "comm_fit" in result and "tax_fit" in result
    # dollar-denominated buckets populated (default model claude-sonnet-5 is priced)
    comm_cell = next(r for r in rows if r["condition"] == "comm")
    assert isinstance(comm_cell["comm_usd"], float)
    bucket_usd = comm_cell["context_usd"] + comm_cell["task_usd"] + comm_cell["comm_usd"] + comm_cell["rework_usd"]
    assert bucket_usd == pytest.approx(comm_cell["dollar_cost"], rel=1e-9)  # additive in $


# --- change 3: pricing ------------------------------------------------------


def test_bucket_dollars_sum_to_total_cost():
    from cooperbench.scaling import pricing

    rt = {
        "context_tokens": 60000,
        "task_tokens": 300,
        "rework_tokens": 40,
        "comm_sent_gen_tokens": 80,
        "comm_recv_tokens": 500,
        "comm_reingest_tokens": 3000,
    }
    usd = pricing.apportion_bucket_dollars(rt, total_cost=0.85, model="claude-sonnet-5")
    assert usd is not None
    assert sum(usd.values()) == pytest.approx(0.85, rel=1e-9)  # additive in $
    assert all(v >= 0 for v in usd.values())
    # unknown model → None (buckets stay token-only)
    assert pricing.apportion_bucket_dollars(rt, 0.85, "some-unpriced-model") is None


# --- change 4: small-sample t-CIs -------------------------------------------


def test_t_crit_uses_t_not_z_for_small_dof():
    crit1, method1 = analysis._t_crit(1)
    assert crit1 == pytest.approx(12.706, abs=1e-2) or method1 == "t-scipy"
    assert crit1 > 5  # never the z=1.96 approximation at dof=1
    crit_big, _ = analysis._t_crit(500)
    assert crit_big == pytest.approx(1.96, abs=0.1)


# --- change 2: coordination-specific fits -----------------------------------


def test_comm_tax_fits_and_curve_and_per_pool():
    rows = _synthetic_rows()
    comm = analysis.fit_comm_quadratic(rows, "comm")
    assert "beta" in comm  # comm_tokens grow as n^2 → estimable
    tax = analysis.fit_tax_quadratic(rows)  # all rows are comm here → no nocomm pairs
    assert "error" in tax or "beta" in tax  # runs end-to-end either way
    curve = analysis.cost_curve(rows)
    assert "N4_comm" in curve and curve["N4_comm"]["dollar_cost"]["n"] == 2
    pp = analysis.per_pool_cost_fits(rows)
    assert "aggregate_beta" in pp


# --- change 1: idempotent eval on resume ------------------------------------


def test_eval_not_recomputed_on_resume(tmp_path, monkeypatch):
    pool = pools.Pool("openai_tiktoken_task", 0, (2, 3))
    eval_calls = {"n": 0}

    def fake_execute_partitioned(repo_name, task_id, assignment, run_name, **kw):
        leaf = tmp_path / "logs" / run_name / f"N{len(assignment)}_{kw['condition']}_r{kw['trial']}"
        leaf.mkdir(parents=True, exist_ok=True)
        for a in assignment:
            (leaf / f"{a}.patch").write_text("")
        return {"result_data": {"log_dir": str(leaf), "total_cost": 0.5, "total_steps": 3, "messages_sent": 0}}

    def counting_eval(repo_name, task_id, assignment, patches, **kw):
        eval_calls["n"] += 1
        return {"all_passed": True, "failure_bucket": "success", "merge": {"status": "clean"}}

    monkeypatch.setattr(experiment, "execute_partitioned", fake_execute_partitioned)
    monkeypatch.setattr(experiment, "test_merged_nway", counting_eval)
    monkeypatch.setattr(experiment, "compute_run_buckets", lambda ld, ids: {"recoverable": False, "run_total": {}})

    kw = dict(
        agents=[1, 2], conditions=("nocomm",), trials=1, logs_dir=str(tmp_path / "logs"), out_dir=str(tmp_path / "res")
    )
    experiment.run_experiment([pool], **kw)
    first = eval_calls["n"]
    assert first == 2  # N=1 + N=2 nocomm cells
    experiment.run_experiment([pool], **kw)  # resume: eval.json cached → no recompute
    assert eval_calls["n"] == first


# --- shared-git: integrated scoring -----------------------------------------


def test_score_team_uses_integrator_and_tracks_best(monkeypatch):
    from cooperbench.scaling import eval_git

    # agent1 integrated 3/4, agent2 integrated 4/4 → team = integrator (agent1),
    # best = agent2.
    canned = {
        "agent1": {"score": 0.75, "n_passed": 3, "k": 4, "all_passed": False, "features": {}, "error": None},
        "agent2": {"score": 1.0, "n_passed": 4, "k": 4, "all_passed": True, "features": {}, "error": None},
    }
    monkeypatch.setattr(eval_git, "test_integrated", lambda r, t, f, p, **kw: canned[_patch_owner(p)])
    res = eval_git.score_team("repo", 0, [1, 2, 3, 4], {"agent1": "a1", "agent2": "a2"})
    assert res["integrator"] == "agent1"
    assert res["score"] == pytest.approx(0.75) and res["all_passed"] is False  # shipped = integrator
    assert res["best_score"] == pytest.approx(1.0) and res["best_all_passed"] is True
    assert res["per_agent_score"] == {"agent1": 0.75, "agent2": 1.0}


def _patch_owner(p):
    return "agent1" if str(p).endswith("a1") else "agent2"


def test_performance_curve_over_n():
    # graded score declines as N grows (the shape the experiment looks for)
    rows = []
    for n, sc in ((1, 1.0), (2, 0.75), (3, 0.5), (4, 0.25)):
        rows.append({"N": n, "score": sc, "all_passed": sc == 1.0, "dollar_cost": 0.5 * n, "condition": "comm"})
    curve = analysis.performance_curve(rows)
    assert curve[1]["mean_score"] == pytest.approx(1.0)
    assert curve[4]["mean_score"] == pytest.approx(0.25)
    assert curve[1]["all_passed_rate"] == pytest.approx(1.0)
    assert curve[4]["all_passed_rate"] == pytest.approx(0.0)


def test_git_experiment_end_to_end(tmp_path, monkeypatch):
    """Shared-git sweep: agents integrate, eval scores one tree graded, curve builds."""
    pool = pools.Pool("openai_tiktoken_task", 0, (1, 2, 3, 4))

    def fake_execute_partitioned(repo_name, task_id, assignment, run_name, **kw):
        assert kw.get("git_enabled") is True  # git threaded through
        leaf = tmp_path / "logs" / run_name / f"N{len(assignment)}_{kw['condition']}_r{kw['trial']}"
        leaf.mkdir(parents=True, exist_ok=True)
        for a in assignment:
            (leaf / f"{a}.patch").write_text("")
        n = len(assignment)
        return {
            "result_data": {
                "log_dir": str(leaf),
                "total_cost": 0.4 * n,
                "total_steps": 5 * n,
                "messages_sent": 0,
                "git_integrated": n > 1,
            }
        }

    def fake_score_team(repo_name, task_id, feature_ids, agent_patches, **kw):
        # integrated score decays with N (more agents → harder to integrate)
        n = len(agent_patches)
        n_pass = max(len(feature_ids) - (n - 1), 0)
        k = len(feature_ids)
        return {
            "score": n_pass / k,
            "n_passed": n_pass,
            "k": k,
            "all_passed": n_pass == k,
            "best_score": n_pass / k,
            "features": {},
            "error": None,
        }

    monkeypatch.setattr(experiment, "execute_partitioned", fake_execute_partitioned)
    monkeypatch.setattr(experiment, "score_team", fake_score_team)
    monkeypatch.setattr(experiment, "compute_run_buckets", lambda ld, ids: {"recoverable": False, "run_total": {}})

    out = tmp_path / "res"
    rows = experiment.run_experiment(
        [pool],
        agents=[1, 2, 3, 4],
        conditions=("comm",),
        trials=1,
        git_enabled=True,
        logs_dir=str(tmp_path / "logs"),
        out_dir=str(out),
    )
    # N=1 always runs as the solo baseline; N>=2 run the comm arm → N∈{1,2,3,4}
    assert {r["N"] for r in rows} == {1, 2, 3, 4}
    # git integration only for N>=2 (N=1 solo has nothing to integrate)
    assert {r["N"] for r in rows if r["git_integrated"]} == {2, 3, 4}
    by_n = {r["N"]: r["score"] for r in rows}
    assert by_n[1] > by_n[4]  # graded score declines from the solo baseline
    result = analysis.run_analysis(rows, out)
    assert "performance_curve" in result and result["performance_curve"][1]["mean_score"] is not None
