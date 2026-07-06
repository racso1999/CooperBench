"""Tests that build_instruction renders the structured block for a schema
and leaves the free-form baseline untouched."""

from cooperbench.agents._coop import build_instruction, load_schema

_AGENTS = ["agent1", "agent2"]


def test_structured_block_renders_schema_fields():
    text = build_instruction("Task", agents=_AGENTS, agent_id="agent1", message_schema=load_schema(None))
    assert "structured messaging" in text.lower()
    assert "--type" in text and "--files" in text and "--summary" in text
    assert "CLAIM" in text  # enum surfaced
    assert "REJECTED" in text  # enforcement is advertised to the agent


def test_none_schema_keeps_freeform_block():
    free = build_instruction("Task", agents=_AGENTS, agent_id="agent1")
    structured = build_instruction("Task", agents=_AGENTS, agent_id="agent1", message_schema=load_schema(None))
    assert free != structured
    # Baseline free-form usage line is unchanged.
    assert 'coop-send <recipient> "message text here"' in free
    assert "structured messaging" not in free.lower()


def test_solo_ignores_schema():
    text = build_instruction("Task", message_schema=load_schema(None))  # no agents -> solo
    assert "structured messaging" not in text.lower()
    assert "Cooperation protocol" not in text


def test_schema_instructions_render_as_workflow(tmp_path):
    """A schema with `instructions` (e.g. plan_handshake) injects them into the
    prompt in place of the default workflow, and coop-await is advertised."""
    p = tmp_path / "s.toml"
    p.write_text(
        'name = "p"\ninstructions = "PLAN BEFORE CODE: step one do X"\n'
        '[[field]]\nname = "type"\nrequired = true\nenum = ["PROPOSE", "ACCEPT"]\n'
    )
    text = build_instruction("Task", agents=_AGENTS, agent_id="agent1", message_schema=load_schema(p))
    assert "PLAN BEFORE CODE: step one do X" in text
    assert "coop-await" in text
