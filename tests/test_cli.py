"""Tests for CLI functionality."""

import sys
from unittest.mock import patch

import pytest

from cooperbench.cli import _generate_run_name


class TestGenerateRunName:
    """Tests for _generate_run_name function."""

    def test_basic_name_generation(self):
        """Test basic run name generation."""
        name = _generate_run_name("solo", "gpt-4o")
        assert name == "solo-msa_v2-gpt-4o"

    def test_with_subset(self):
        """Test name generation with subset."""
        name = _generate_run_name("solo", "gpt-4o", subset="lite")
        assert name == "solo-msa_v2-gpt-4o-lite"

    def test_with_repo(self):
        """Test name generation with repo filter."""
        name = _generate_run_name("coop", "gpt-4o", repo="llama_index_task")
        assert name == "coop-msa_v2-gpt-4o-llama-index"

    def test_with_task(self):
        """Test name generation with task filter."""
        name = _generate_run_name("solo", "gpt-4o", repo="pillow_task", task=25)
        assert name == "solo-msa_v2-gpt-4o-pillow-25"

    def test_with_task_zero(self):
        """Test name generation with task ID 0 (valid task ID)."""
        name = _generate_run_name("solo", "gpt-4o", repo="openai_tiktoken_task", task=0)
        assert name == "solo-msa_v2-gpt-4o-openai-tiktoken-0"

    def test_with_all_options(self):
        """Test name generation with all options."""
        name = _generate_run_name("coop", "gemini/gemini-3-flash-preview", subset="lite", repo="pillow_task", task=25)
        assert name == "coop-msa_v2-gemini-3-flash-lite-pillow-25"

    def test_cleans_model_name(self):
        """Test that model names are cleaned."""
        name = _generate_run_name("solo", "gemini/gemini-3-flash-preview")
        assert "gemini-3-flash" in name
        assert "preview" not in name
        assert "/" not in name

    def test_cleans_repo_name(self):
        """Test that repo names are cleaned."""
        name = _generate_run_name("solo", "gpt-4o", repo="llama_index_task")
        assert "llama-index" in name
        assert "_task" not in name

    def test_different_settings(self):
        """Test coop vs solo settings."""
        solo_name = _generate_run_name("solo", "gpt-4o")
        coop_name = _generate_run_name("coop", "gpt-4o")
        assert solo_name.startswith("solo-msa_v2-")
        assert coop_name.startswith("coop-msa_v2-")

    def test_structured_messaging_name_includes_schema(self):
        """Structured-messaging arms are disambiguated by schema name."""
        name = _generate_run_name("coop", "gpt-4o", message_schema_name="semi_structured_v1")
        assert "struct-semi_structured_v1" in name
        # free-form (no schema) stays clean
        assert "struct-" not in _generate_run_name("coop", "gpt-4o")


class TestStructuredMessagingCLI:
    """Tests for the --structured-messaging flag wiring."""

    def test_mutually_exclusive_with_no_messaging(self):
        from cooperbench.cli import main

        argv = ["cooperbench", "run", "--structured-messaging", "--no-messaging", "--subset", "nano"]
        with patch.object(sys, "argv", argv):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2  # argparse usage error

    def test_flag_threads_schema_into_run(self, monkeypatch):
        """--structured-messaging loads the default schema and passes it to run()."""
        from cooperbench import cli

        captured = {}

        def fake_run(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("cooperbench.runner.run", fake_run)
        argv = [
            "cooperbench",
            "run",
            "--setting",
            "coop",
            "--subset",
            "nano",
            "-a",
            "claude_code",
            "-m",
            "claude-sonnet-5",
            "--structured-messaging",
        ]
        with patch.object(sys, "argv", argv):
            cli.main()
        assert captured.get("message_schema") is not None
        assert captured["message_schema"]["name"] == "semi_structured_v1"
        assert captured["messaging_enabled"] is True

    def test_no_flag_means_no_schema(self, monkeypatch):
        from cooperbench import cli

        captured = {}
        monkeypatch.setattr("cooperbench.runner.run", lambda **kw: captured.update(kw))
        argv = ["cooperbench", "run", "--setting", "coop", "--subset", "nano", "-a", "claude_code", "-m", "x"]
        with patch.object(sys, "argv", argv):
            cli.main()
        assert captured.get("message_schema") is None


class TestCLI:
    """Tests for CLI."""

    def test_cli_module_importable(self):
        """Test that CLI module is importable."""
        from cooperbench import cli

        assert hasattr(cli, "main")

    def test_cli_help(self):
        """Test CLI help output."""
        from cooperbench.cli import main

        with patch.object(sys, "argv", ["cooperbench", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # --help should exit with 0
            assert exc_info.value.code == 0

    def test_cli_run_subcommand_exists(self):
        """Test run subcommand exists."""
        from cooperbench.cli import main

        with patch.object(sys, "argv", ["cooperbench", "run", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_cli_eval_subcommand_exists(self):
        """Test eval subcommand exists."""
        from cooperbench.cli import main

        with patch.object(sys, "argv", ["cooperbench", "eval", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
