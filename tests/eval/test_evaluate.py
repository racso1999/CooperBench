"""Unit tests for cooperbench.eval.evaluate module."""

import json
from unittest.mock import patch

import pytest

from cooperbench.eval import evaluate


class TestEvaluate:
    """Tests for evaluate function."""

    def test_evaluate_requires_name(self):
        """Test that evaluate requires run_name."""
        with pytest.raises(TypeError):
            evaluate()  # type: ignore

    def test_evaluate_handles_no_runs(self):
        """Test that evaluate handles case with no runs gracefully."""
        with patch("cooperbench.eval.evaluate.discover_runs", return_value=[]):
            # Should not raise, just do nothing
            evaluate(run_name="nonexistent-run")


class TestEvalResultSchema:
    """Tests for evaluation result schema."""

    def test_eval_json_schema(self, tmp_path):
        """Test that eval.json follows expected schema."""
        eval_result = {
            "run_name": "test-run",
            "repo": "test_repo",
            "task_id": 1,
            "features": [1, 2],
            "setting": "coop",
            "merge_status": "success",
            "test_results": {
                "feature1": {"passed": 5, "failed": 0, "total": 5},
                "feature2": {"passed": 3, "failed": 1, "total": 4},
            },
            "overall_passed": True,
            "evaluated_at": "2026-01-31T12:00:00",
        }

        eval_file = tmp_path / "eval.json"
        eval_file.write_text(json.dumps(eval_result))

        loaded = json.loads(eval_file.read_text())
        assert "merge_status" in loaded
        assert "test_results" in loaded
        assert "overall_passed" in loaded


class TestIndependentPersistence:
    """The integrated pipeline persists the pre-merge independent per-feature
    results into eval.json, and threads the run_independent flag through."""

    def _run_info(self, tmp_path):
        log_dir = tmp_path / "run" / "coop" / "repo" / "1" / "f1_f2"
        log_dir.mkdir(parents=True)
        (log_dir / "agent1.patch").write_text("diff --git a/x b/x\n+1\n")
        (log_dir / "agent2.patch").write_text("diff --git a/y b/y\n+2\n")
        return {"log_dir": str(log_dir), "setting": "coop", "repo": "repo", "task_id": 1, "features": [1, 2]}, log_dir

    def _fake_result(self):
        return {
            "apply_status": {"agent1": "applied", "agent2": "applied"},
            "merge": {"status": "conflicts", "strategy": "naive"},
            "feature1": {"passed": False},
            "feature2": {"passed": False},
            "feature1_independent": {"passed": True, "tests_passed": 7, "tests_failed": 0, "reason": None},
            "feature2_independent": {"passed": False, "tests_passed": 4, "tests_failed": 1, "reason": None},
            "both_passed": False,
            "error": None,
        }

    def test_persists_independent_fields(self, tmp_path):
        from cooperbench.eval.evaluate import _evaluate_single

        run_info, log_dir = self._run_info(tmp_path)
        captured = {}

        def fake(**kwargs):
            captured.update(kwargs)
            return self._fake_result()

        with patch("cooperbench.eval.evaluate.test_merged", side_effect=fake):
            _evaluate_single(run_info, force=True)

        saved = json.loads((log_dir / "eval.json").read_text())
        assert saved["feature1_independent"]["passed"] is True
        assert saved["feature1_independent"]["tests_passed"] == 7
        assert saved["feature2_independent"]["tests_failed"] == 1
        assert captured["run_independent"] is True

    def test_no_independent_flag_threads_through(self, tmp_path):
        from cooperbench.eval.evaluate import _evaluate_single

        run_info, _ = self._run_info(tmp_path)
        captured = {}

        def fake(**kwargs):
            captured.update(kwargs)
            return self._fake_result()

        with patch("cooperbench.eval.evaluate.test_merged", side_effect=fake):
            _evaluate_single(run_info, force=True, run_independent=False)

        assert captured["run_independent"] is False
