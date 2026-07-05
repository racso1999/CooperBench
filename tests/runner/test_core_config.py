"""Tests that the run config records the structured-messaging schema."""

import json

from cooperbench.agents._coop import load_schema
from cooperbench.runner.core import _save_config


def test_save_config_records_full_structured_schema(tmp_path):
    schema = load_schema(None)
    _save_config(
        tmp_path,
        "run",
        "claude_code",
        "m",
        "coop",
        2,
        5,
        messaging_enabled=True,
        message_schema=schema,
    )
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["messaging_mode"] == "structured"
    # full field definitions are persisted, not just the name
    assert cfg["message_schema"]["name"] == "semi_structured_v1"
    assert any(f["name"] == "files" for f in cfg["message_schema"]["fields"])


def test_save_config_freeform_has_null_schema(tmp_path):
    _save_config(tmp_path, "r", "a", "m", "coop", 2, 1, messaging_enabled=True, message_schema=None)
    cfg = json.loads((tmp_path / "config.json").read_text())
    assert cfg["messaging_mode"] == "free"
    assert cfg["message_schema"] is None


def test_save_config_messaging_off(tmp_path):
    _save_config(tmp_path, "r", "a", "m", "coop", 2, 1, messaging_enabled=False, message_schema=None)
    assert json.loads((tmp_path / "config.json").read_text())["messaging_mode"] == "off"
