"""Token-bucket instrumentation from saved Claude Code streams.

**Scope / honesty note (mirrors INTEGRATION_MAP §6).** CooperBench records only
terminating per-agent aggregates.  The four buckets the scaling design asks for
(``context`` / ``task`` / ``comm`` / ``rework``) are **not** recorded and are
derived here, post-hoc, from the per-agent raw stream that only the ``claude_code``
adapter persists (``<agent_id>_stream.jsonl`` + ``<agent_id>_sent.jsonl``).  Each
bucket is a *documented proxy*, not ground truth:

* ``context`` — the resident context at the first assistant turn (system prompt +
  tool schemas + task spec): the linear floor, paid once and carried.  Proxy:
  ``cache_read_input_tokens`` of turn 0.  Clean at turn 0; blurs as the agent reads
  more files, so growth beyond turn 0 is attributed to ``task``, not ``context``.
* ``comm`` — SENT (message content tokens, from ``_sent.jsonl``) + RECEIVED
  (``coop-recv`` tool-result payloads) + RE-INGESTION (each received payload is
  re-paid as cache-read every subsequent turn until compaction).  Recoverable
  because comm is discrete ``coop-*`` Bash tool events in the stream.
* ``rework`` — **weakest, a heuristic**: output tokens of turns that edit an
  already-edited file *after* an inbound message was delivered.  Over/under-counts
  when a re-edit is coincidental or reasoning-driven rather than message-driven.
* ``task`` — residual generation (total output minus comm-send generation minus
  rework).

To keep the numbers auditable, every derived bucket ships alongside the **raw
per-turn table** and the **raw feeder signals** (n_sends, n_recvs, n_message_reads,
n_reedits_after_recv), so the bucket formulas can be recomputed or discarded
downstream without re-running anything.  Token counts for message text use a
``ceil(len/4)`` character estimate (documented; no tokenizer dependency).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_COMPACTION_DROP = 0.5  # cache_read falling below half the prior turn ⇒ treat as compaction


def _est_tokens(text: str) -> int:
    """Rough token estimate for message text (documented ~4 chars/token)."""
    return math.ceil(len(text) / 4) if text else 0


@dataclass
class Turn:
    """One deduplicated assistant turn with its usage + actions."""

    index: int
    output_tokens: int = 0
    input_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    tools: list[str] = field(default_factory=list)
    edited_files: list[str] = field(default_factory=list)
    sent: bool = False  # issued coop-send / coop-broadcast
    recv: bool = False  # issued coop-recv
    recv_payload_tokens: int = 0  # tokens delivered by this turn's coop-recv result
    recv_messages: int = 0  # number of inbound messages delivered this turn
    is_rework: bool = False


@dataclass
class AgentBuckets:
    """Per-agent bucket decomposition + raw signals (all serialisable)."""

    agent_id: str
    n_turns: int = 0
    # --- raw totals (exact, from stream usage) ---
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_input: int = 0
    # --- buckets (documented proxies) ---
    context_tokens: int = 0
    task_tokens: int = 0
    comm_tokens: int = 0
    rework_tokens: int = 0
    # --- comm breakdown ---
    comm_sent_tokens: int = 0
    comm_recv_tokens: int = 0
    comm_reingest_tokens: int = 0
    comm_sent_gen_tokens: int = 0
    # --- raw feeder signals (for the driver regression) ---
    n_sends: int = 0
    n_recvs: int = 0
    n_messages_read: int = 0  # inbound messages × persistence (re-ingestion count)
    n_reedits_after_recv: int = 0
    # per-turn table, for full auditability
    turns: list[dict] = field(default_factory=list)


def _iter_assistant_turns(stream_lines: list[str]) -> list[Turn]:
    """Parse a claude_code stream into deduplicated assistant turns.

    Streaming emits an assistant message id multiple times; we keep the final
    (max output_tokens) occurrence per id and pair each ``coop-recv`` tool_use
    with the tool_result that follows it (matched by tool_use_id).
    """
    events = []
    for ln in stream_lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            events.append(json.loads(ln))
        except json.JSONDecodeError:
            continue

    # First pass: collect tool_result payloads by tool_use_id (from user events).
    tool_results: dict[str, str] = {}
    for e in events:
        if e.get("type") != "user":
            continue
        msg = e.get("message") if isinstance(e.get("message"), dict) else None
        content = msg.get("content") if msg else None
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tid = b.get("tool_use_id")
                c = b.get("content", "")
                if isinstance(c, list):
                    c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                if tid:
                    tool_results[tid] = str(c)

    # Second pass: dedup assistant turns by message id, keep final usage.
    by_id: dict[str, Turn] = {}
    order: list[str] = []
    for e in events:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") if isinstance(e.get("message"), dict) else None
        if not msg:
            continue
        mid = msg.get("id") or f"anon{len(order)}"
        usage = msg.get("usage") or {}
        out = int(usage.get("output_tokens") or 0)
        if mid not in by_id:
            by_id[mid] = Turn(index=len(order))
            order.append(mid)
        turn = by_id[mid]
        # keep the richest (final) usage snapshot for this streamed message
        if out >= turn.output_tokens:
            turn.output_tokens = out
            turn.input_tokens = int(usage.get("input_tokens") or 0)
            turn.cache_read = int(usage.get("cache_read_input_tokens") or 0)
            turn.cache_write = int(usage.get("cache_creation_input_tokens") or 0)
        for blk in msg.get("content") or []:
            if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                continue
            name = blk.get("name", "")
            if name not in turn.tools:
                turn.tools.append(name)
            inp = blk.get("input") or {}
            if name == "Bash":
                cmd = str(inp.get("command", ""))
                if "coop-send" in cmd or "coop-broadcast" in cmd:
                    turn.sent = True
                if "coop-recv" in cmd:
                    turn.recv = True
                    payload = tool_results.get(blk.get("id"), "")
                    turn.recv_payload_tokens += _est_tokens(payload)
                    turn.recv_messages += payload.count("Message from") or (1 if payload.strip() else 0)
            elif name in _EDIT_TOOLS:
                fp = inp.get("file_path") or inp.get("path")
                if fp:
                    turn.edited_files.append(str(fp))

    return [by_id[m] for m in order]


def compute_agent_buckets(log_dir: str | Path, agent_id: str) -> AgentBuckets | None:
    """Derive buckets for one agent from its saved stream, or None if absent."""
    log_dir = Path(log_dir)
    stream_path = log_dir / f"{agent_id}_stream.jsonl"
    if not stream_path.exists():
        return None
    turns = _iter_assistant_turns(stream_path.read_text().splitlines())
    ab = AgentBuckets(agent_id=agent_id, n_turns=len(turns))
    if not turns:
        return ab

    # --- exact totals ---
    ab.total_output = sum(t.output_tokens for t in turns)
    ab.total_cache_read = sum(t.cache_read for t in turns)
    ab.total_cache_write = sum(t.cache_write for t in turns)
    ab.total_input = sum(t.input_tokens for t in turns)

    # --- context floor: resident context at turn 0 ---
    ab.context_tokens = turns[0].cache_read + turns[0].cache_write + turns[0].input_tokens

    # --- rework heuristic: edit of an already-edited file after an inbound msg ---
    seen_files: set[str] = set()
    inbound_seen = False
    for t in turns:
        if t.recv and t.recv_messages:
            inbound_seen = True
        reworked = inbound_seen and any(f in seen_files for f in t.edited_files)
        if reworked:
            t.is_rework = True
            ab.rework_tokens += t.output_tokens
            ab.n_reedits_after_recv += 1
        seen_files.update(t.edited_files)

    # --- comm: received payloads + re-ingestion, with compaction detection ---
    for i, t in enumerate(turns):
        if t.recv and t.recv_payload_tokens:
            ab.comm_recv_tokens += t.recv_payload_tokens
            # persistence: turns after i until compaction (cache_read halving) or end
            persistence = 0
            for j in range(i + 1, len(turns)):
                if turns[j].cache_read < turns[j - 1].cache_read * _COMPACTION_DROP:
                    break  # context compacted; message no longer resident
                persistence += 1
            ab.comm_reingest_tokens += t.recv_payload_tokens * persistence
            ab.n_messages_read += t.recv_messages * (1 + persistence)
        if t.sent:
            ab.n_sends += 1
            ab.comm_sent_gen_tokens += t.output_tokens
        if t.recv:
            ab.n_recvs += 1

    # --- sent message content tokens (from the send-log; exact content sizes) ---
    sent_path = log_dir / f"{agent_id}_sent.jsonl"
    if sent_path.exists():
        for ln in sent_path.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            ab.comm_sent_tokens += _est_tokens(str(rec.get("content", "")))

    ab.comm_tokens = ab.comm_sent_tokens + ab.comm_recv_tokens + ab.comm_reingest_tokens

    # --- task = residual generation (output not spent on comm-send or rework) ---
    ab.task_tokens = max(ab.total_output - ab.comm_sent_gen_tokens - ab.rework_tokens, 0)

    ab.turns = [asdict(t) for t in turns]
    return ab


def compute_run_buckets(log_dir: str | Path, agent_ids: list[str]) -> dict:
    """Aggregate per-agent buckets + a run total.

    Returns ``{"agents": {id: {...}}, "run_total": {...}, "recoverable": bool}``.
    ``recoverable`` is False when no agent stream was found (non-``claude_code``
    agent, or streams not persisted) — callers should treat buckets as missing,
    not zero, in that case.
    """
    per_agent: dict[str, dict] = {}
    any_stream = False
    for a in agent_ids:
        ab = compute_agent_buckets(log_dir, a)
        if ab is None:
            continue
        any_stream = True
        d = asdict(ab)
        d.pop("turns", None)  # keep the run summary compact; per-turn stays per-agent
        per_agent[a] = d

    agg_keys = [
        "context_tokens",
        "task_tokens",
        "comm_tokens",
        "rework_tokens",
        "comm_sent_tokens",
        "comm_recv_tokens",
        "comm_reingest_tokens",
        "comm_sent_gen_tokens",
        "total_output",
        "total_cache_read",
        "total_cache_write",
        "total_input",
        "n_sends",
        "n_recvs",
        "n_messages_read",
        "n_reedits_after_recv",
    ]
    run_total = {k: sum(d.get(k, 0) for d in per_agent.values()) for k in agg_keys}
    return {"agents": per_agent, "run_total": run_total, "recoverable": any_stream}
