"""Tests for the container-side coop_msg CLI in structured mode.

Uses fakeredis (a dev dep) in place of a real Redis, and drives the CLI's
``main()`` exactly as the in-container ``coop-send`` wrapper would.
"""

import json

import fakeredis

from cooperbench.agents._coop import coop_msg, load_schema, to_container_json


def _setup(monkeypatch, tmp_path, *, structured):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(coop_msg.redis, "from_url", lambda url: fake)
    monkeypatch.setenv("COOP_REDIS_URL", "redis://stub")
    monkeypatch.setenv("COOP_AGENT_ID", "agent1")
    monkeypatch.setenv("COOP_AGENTS", "agent1,agent2")
    log = tmp_path / "sent.jsonl"
    monkeypatch.setenv("COOP_LOG_PATH", str(log))
    if structured:
        sp = tmp_path / "schema.json"
        sp.write_text(to_container_json(load_schema(None)))
        monkeypatch.setenv("COOP_SCHEMA_PATH", str(sp))
    else:
        monkeypatch.delenv("COOP_SCHEMA_PATH", raising=False)
    return fake, log


def _inbox(fake, agent="agent2"):
    return [json.loads(x) for x in fake.lrange(f"{agent}:inbox", 0, -1)]


class TestStructuredSend:
    def test_valid_send_stores_fields_and_kind_and_logs(self, monkeypatch, tmp_path):
        fake, log = _setup(monkeypatch, tmp_path, structured=True)
        rc = coop_msg.main(["send", "agent2", "--type", "CLAIM", "--files", "a.py", "--summary", "own parser"])
        assert rc == 0
        msgs = _inbox(fake)
        assert len(msgs) == 1
        assert msgs[0]["kind"] == "CLAIM"
        assert msgs[0]["fields"] == {"type": "CLAIM", "files": "a.py", "summary": "own parser"}
        assert log.exists() and "CLAIM" in log.read_text()

    def test_missing_required_rejected_no_send_no_log(self, monkeypatch, tmp_path, capsys):
        fake, log = _setup(monkeypatch, tmp_path, structured=True)
        rc = coop_msg.main(["send", "agent2", "--files", "a.py"])  # no --type/--summary
        assert rc == 1
        assert _inbox(fake) == []
        assert not log.exists()
        assert "REJECTED" in capsys.readouterr().err

    def test_out_of_enum_rejected(self, monkeypatch, tmp_path):
        fake, log = _setup(monkeypatch, tmp_path, structured=True)
        rc = coop_msg.main(["send", "agent2", "--type", "BOGUS", "--files", "a.py", "--summary", "x"])
        assert rc == 1
        assert _inbox(fake) == []
        assert not log.exists()

    def test_optional_field_omitted_is_ok(self, monkeypatch, tmp_path):
        fake, _ = _setup(monkeypatch, tmp_path, structured=True)
        rc = coop_msg.main(["send", "agent2", "--type", "STATUS", "--files", "a.py", "--summary", "wip"])
        assert rc == 0
        assert "blocked_on" not in _inbox(fake)[0]["fields"]

    def test_broadcast_reaches_peers_not_self(self, monkeypatch, tmp_path):
        fake, _ = _setup(monkeypatch, tmp_path, structured=True)
        rc = coop_msg.main(["broadcast", "--type", "INTENT", "--files", "a.py", "--summary", "plan"])
        assert rc == 0
        assert len(_inbox(fake, "agent2")) == 1
        assert _inbox(fake, "agent1") == []


class TestAwait:
    def test_await_drains_present_message(self, monkeypatch, tmp_path):
        fake, _ = _setup(monkeypatch, tmp_path, structured=False)
        fake.rpush("agent1:inbox", json.dumps({"from": "agent2", "content": "hi", "kind": "ACCEPT"}))
        rc = coop_msg.main(["await"])
        assert rc == 0
        assert fake.llen("agent1:inbox") == 0  # drained

    def test_await_timeout_prints_empty_list(self, monkeypatch, tmp_path, capsys):
        _setup(monkeypatch, tmp_path, structured=False)
        rc = coop_msg.main(["await", "--timeout", "0"])
        assert rc == 0
        assert "[]" in capsys.readouterr().out


class TestFreeFormUnchanged:
    def test_freeform_send_has_no_fields_or_kind(self, monkeypatch, tmp_path):
        fake, _ = _setup(monkeypatch, tmp_path, structured=False)
        rc = coop_msg.main(["send", "agent2", "hello there"])
        assert rc == 0
        msg = _inbox(fake)[0]
        assert msg["content"] == "hello there"
        assert "fields" not in msg and "kind" not in msg
