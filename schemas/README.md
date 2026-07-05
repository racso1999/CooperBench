# Structured-messaging schemas

Ready-to-run message schemas for `--structured-messaging`. Each file defines the
structure agents must use when they message each other in `coop` mode; the
container-side messaging CLI hard-rejects messages that omit a required field or
violate an enum, so "structure was actually used" is not a confound.

Point the flag at any of these (or copy one and edit it):

```bash
uv run cooperbench run --setting coop -a claude_code -m claude-sonnet-5 \
  --subset nano -c 2 --structured-messaging schemas/ownership_first.toml
```

Omitting the path uses the bundled default,
`src/cooperbench/agents/_coop/message_schema.toml` (`semi_structured_v1`).

## What's here

| File | `name` | Idea |
|---|---|---|
| *(bundled default)* | `semi_structured_v1` | Semi-structured slots: type + files + summary + blocked_on. The general-purpose starting point. |
| `typed_only.toml` | `typed_v1` | Just a required message **type** tag + free-text body. Isolates whether type-tagging alone helps. |
| `ownership_first.toml` | `ownership_first_v1` | Heavy structure aimed squarely at textual merge conflicts: an explicit file/function **ownership claim** on every message. |
| `minimal.toml` | `minimal_v1` | One free-text field. Near-baseline "structure floor" — tests whether *any* structure beats free-form. |

## A/B'ing them

- Each schema's `name` is stamped into the auto run-name as `struct-<name>`, so
  arms land in distinct `logs/` dirs and don't collide. **Change the `name`
  whenever you change a schema.**
- The full schema (field definitions) is saved to `logs/<run>/config.json`
  (`message_schema`), and each pair's `result.json` records the schema `name`
  plus `messages_by_kind` — so a run is self-documenting.
- Compare a structured arm against the free-form baseline (no flag) or against
  another schema, using `scripts/nano/analyze.py` on merge-clean rate.

## Field reference

Each `[[field]]` is one slot the agent fills via `coop-send --<name> <value>`:

- `name` (required) — identifier; becomes the `--<name>` flag. Must match
  `[A-Za-z][A-Za-z0-9_]*`. Avoid `help` (collides with the CLI's `-h`).
- `required` (default `false`) — if true, a message omitting it is rejected.
- `enum` (optional) — if present, the value must be one of these strings.
- `description` — shown to the agent in its prompt.
