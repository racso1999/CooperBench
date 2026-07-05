#!/usr/bin/env python3
"""Tiny messaging CLI for Claude Code to use inside the agent container.

Mirrors the semantics of CooperBench's host-side ``MessagingConnector``
(Redis lists, one inbox per agent, optional ``#run:<id>`` namespace
prefix) but lives in the container so the in-process LLM can invoke it
via Bash.

Usage:
    coop-send <recipient> <content>      # send to one agent
    coop-broadcast <content>             # send to every other agent
    coop-recv                            # drain this agent's inbox (JSON list)
    coop-peek                            # count unread messages
    coop-agents                          # list all agent ids

Config is read from environment variables (set by the adapter):
    COOP_REDIS_URL   redis://host[:port][/db][#run:<id>]
    COOP_AGENT_ID    this agent's id (e.g. "agent1")
    COOP_AGENTS      comma-separated list (e.g. "agent1,agent2")
    COOP_LOG_PATH    optional; if set, every successful send is appended
                     to this file as one JSON line for the host adapter
                     to harvest after the run.
    COOP_SCHEMA_PATH optional; path to a JSON schema (written by the adapter).
                     When set, ``send``/``broadcast`` take one ``--<field>``
                     flag per schema field and REJECT (nonzero exit, no send)
                     messages that omit a required field or use an out-of-enum
                     value.  When unset, messaging is free-form (legacy).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

import redis


def _client_and_prefix() -> tuple[redis.Redis, str]:
    url = os.environ["COOP_REDIS_URL"]
    if "#" in url:
        url, prefix = url.split("#", 1)
        prefix = prefix + ":"
    else:
        prefix = ""
    return redis.from_url(url), prefix


def _agent_id() -> str:
    return os.environ["COOP_AGENT_ID"]


def _agents() -> list[str]:
    raw = os.environ.get("COOP_AGENTS", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


def _schema() -> dict[str, Any] | None:
    """Load the structured-messaging schema, or None for free-form mode."""
    path = os.environ.get("COOP_SCHEMA_PATH")
    if not path:
        return None
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _print_schema(schema: dict[str, Any]) -> None:
    print(f"  required message format (schema '{schema.get('name')}'):", file=sys.stderr)
    for f in schema.get("fields", []):
        req = "required" if f.get("required") else "optional"
        enum = f" one of {f['enum']}" if f.get("enum") else ""
        print(f"    --{f['name']} <value>  [{req}]{enum}  {f.get('description', '')}", file=sys.stderr)


def _collect_fields(schema: dict[str, Any], args: argparse.Namespace) -> dict[str, str] | None:
    """Validate the ``--<field>`` args against the schema.

    Returns the field dict on success, or None (after printing the problem
    and the schema to stderr) if a required field is missing or an enum is
    violated — the caller then aborts WITHOUT sending.
    """
    fields: dict[str, str] = {}
    errors: list[str] = []
    for f in schema.get("fields", []):
        val = getattr(args, f["name"], None)
        if val is None or val == "":
            if f.get("required"):
                errors.append(f"missing required field --{f['name']} ({f.get('description', '')})")
            continue
        enum = f.get("enum")
        if enum and val not in enum:
            errors.append(f"--{f['name']} must be one of {enum} (got {val!r})")
            continue
        fields[f["name"]] = val
    if errors:
        print("coop-send: message REJECTED — does not match the required schema:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        _print_schema(schema)
        return None
    return fields


def _render_fields(fields: dict[str, str]) -> str:
    """Human-readable rendering stored as the message body (for coop-recv)."""
    return "\n".join(f"{k}: {v}" for k, v in fields.items())


def _kind(schema: dict[str, Any], fields: dict[str, str]) -> str | None:
    """Value of the first enum field, treated as the message 'type'/kind."""
    for f in schema.get("fields", []):
        if f.get("enum"):
            return fields.get(f["name"])
    return None


def _log_send(entry: dict[str, Any]) -> None:
    path = os.environ.get("COOP_LOG_PATH")
    if not path:
        return
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        # Logging failure shouldn't interrupt the send.
        pass


def _send(
    client: redis.Redis,
    prefix: str,
    recipient: str,
    content: str,
    *,
    fields: dict[str, str] | None = None,
    kind: str | None = None,
) -> None:
    entry: dict[str, Any] = {
        "from": _agent_id(),
        "to": recipient,
        "content": content,
        "timestamp": time.time(),
        "timestamp_iso": datetime.now().isoformat(),
    }
    if fields is not None:
        entry["fields"] = fields
    if kind is not None:
        entry["kind"] = kind
    client.rpush(f"{prefix}{recipient}:inbox", json.dumps(entry))
    _log_send(entry)


def cmd_send(args: argparse.Namespace) -> int:
    client, prefix = _client_and_prefix()
    schema = _schema()
    if schema is not None:
        fields = _collect_fields(schema, args)
        if fields is None:
            return 1
        _send(client, prefix, args.recipient, _render_fields(fields), fields=fields, kind=_kind(schema, fields))
    else:
        content = args.content if args.content is not None else sys.stdin.read()
        _send(client, prefix, args.recipient, content)
    print(f"sent to {args.recipient}", file=sys.stderr)
    return 0


def cmd_broadcast(args: argparse.Namespace) -> int:
    client, prefix = _client_and_prefix()
    schema = _schema()
    me = _agent_id()
    if schema is not None:
        fields = _collect_fields(schema, args)
        if fields is None:
            return 1
        content = _render_fields(fields)
        kind = _kind(schema, fields)
        for agent in _agents():
            if agent == me:
                continue
            _send(client, prefix, agent, content, fields=fields, kind=kind)
    else:
        content = args.content if args.content is not None else sys.stdin.read()
        for agent in _agents():
            if agent == me:
                continue
            _send(client, prefix, agent, content)
    return 0


def cmd_recv(_args: argparse.Namespace) -> int:
    client, prefix = _client_and_prefix()
    key = f"{prefix}{_agent_id()}:inbox"
    messages = []
    while True:
        raw = client.lpop(key)
        if raw is None:
            break
        try:
            messages.append(json.loads(raw))
        except json.JSONDecodeError:
            messages.append({"content": raw.decode() if isinstance(raw, bytes) else raw})
    print(json.dumps(messages, indent=2))
    return 0


def cmd_peek(_args: argparse.Namespace) -> int:
    client, prefix = _client_and_prefix()
    print(client.llen(f"{prefix}{_agent_id()}:inbox"))
    return 0


def cmd_agents(_args: argparse.Namespace) -> int:
    for agent in _agents():
        print(agent)
    return 0


def _add_field_args(parser: argparse.ArgumentParser, schema: dict[str, Any]) -> None:
    """Add one ``--<field>`` option per schema field (validated in the command,
    not by argparse, so we can print the full schema on a violation)."""
    for f in schema.get("fields", []):
        help_txt = f.get("description", "")
        if f.get("enum"):
            help_txt = f"{help_txt} (one of {', '.join(f['enum'])})".strip()
        parser.add_argument(f"--{f['name']}", default=None, help=help_txt)


def main(argv: list[str] | None = None) -> int:
    schema = _schema()
    parser = argparse.ArgumentParser(prog="coop-msg")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_send = sub.add_parser("send")
    p_send.add_argument("recipient")
    if schema is not None:
        _add_field_args(p_send, schema)
    else:
        p_send.add_argument("content", nargs="?", default=None)
    p_send.set_defaults(func=cmd_send)

    p_bcast = sub.add_parser("broadcast")
    if schema is not None:
        _add_field_args(p_bcast, schema)
    else:
        p_bcast.add_argument("content", nargs="?", default=None)
    p_bcast.set_defaults(func=cmd_broadcast)

    sub.add_parser("recv").set_defaults(func=cmd_recv)
    sub.add_parser("peek").set_defaults(func=cmd_peek)
    sub.add_parser("agents").set_defaults(func=cmd_agents)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
