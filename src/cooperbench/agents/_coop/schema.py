"""Host-side loader/validator for structured-messaging schemas.

A *schema* declares the structure agents must use when they message each
other in coop mode (``--structured-messaging``).  This module is the single
source of truth for schema semantics on the host: it parses the editable
file (TOML or JSON), validates it, and normalizes it to a plain dict that is

  * rendered into the agent prompt (see ``prompt._structured_coop_block``), and
  * serialized as JSON into the task container, where the stdlib-only
    ``coop_msg.py`` validator enforces it.

Container code never imports this module (it can only import redis+stdlib);
it reads the normalized JSON instead, so the two can't drift.

Normalized schema shape::

    {
      "name": "semi_structured_v1",
      "fields": [
        {"name": "type", "required": True,
         "enum": ["CLAIM", ...], "description": "..."},
        {"name": "files", "required": True,
         "enum": None, "description": "..."},
        ...
      ],
    }
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import tomllib

# Field names become ``--<name>`` CLI flags and argparse dests, so they must
# be plain identifiers.
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

DEFAULT_SCHEMA_PATH = Path(__file__).parent / "message_schema.toml"


class SchemaError(ValueError):
    """Raised when a schema file is missing, unparseable, or malformed."""


def _parse_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SchemaError(f"message schema file not found: {path}")
    try:
        raw = path.read_bytes()
    except OSError as e:  # pragma: no cover - unusual FS errors
        raise SchemaError(f"could not read message schema {path}: {e}") from e
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            return json.loads(raw.decode("utf-8"))
        # Default to TOML for .toml and anything else.
        return tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise SchemaError(f"could not parse message schema {path}: {e}") from e


def _normalize(data: dict[str, Any], source: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaError(f"{source}: top level must be a table/object")

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SchemaError(f"{source}: 'name' is required and must be a non-empty string")

    # TOML array-of-tables lands under 'field'; JSON authors may use 'fields'.
    raw_fields = data.get("field", data.get("fields"))
    if not isinstance(raw_fields, list) or not raw_fields:
        raise SchemaError(f"{source}: at least one [[field]] (or 'fields' entry) is required")

    seen: set[str] = set()
    fields: list[dict[str, Any]] = []
    for i, f in enumerate(raw_fields):
        if not isinstance(f, dict):
            raise SchemaError(f"{source}: field #{i + 1} must be a table/object")
        fname = f.get("name")
        if not isinstance(fname, str) or not _FIELD_NAME_RE.match(fname):
            raise SchemaError(f"{source}: field #{i + 1} 'name' must match [A-Za-z][A-Za-z0-9_]* (got {fname!r})")
        if fname in seen:
            raise SchemaError(f"{source}: duplicate field name {fname!r}")
        seen.add(fname)

        required = f.get("required", False)
        if not isinstance(required, bool):
            raise SchemaError(f"{source}: field {fname!r} 'required' must be a boolean")

        enum = f.get("enum")
        if enum is not None:
            if not isinstance(enum, list) or not enum or not all(isinstance(v, str) for v in enum):
                raise SchemaError(f"{source}: field {fname!r} 'enum' must be a non-empty list of strings")

        description = f.get("description", "")
        if not isinstance(description, str):
            raise SchemaError(f"{source}: field {fname!r} 'description' must be a string")

        fields.append(
            {
                "name": fname,
                "required": required,
                "enum": list(enum) if enum is not None else None,
                "description": description,
            }
        )

    return {"name": name, "fields": fields}


def load_schema(path: str | Path | None) -> dict[str, Any]:
    """Load, parse, and validate a schema file into a normalized dict.

    ``path=None`` loads the bundled default schema.  Raises ``SchemaError``
    on any problem (caller should surface it and abort rather than silently
    falling back to free-form, which would confound an A/B comparison).
    """
    p = Path(path) if path is not None else DEFAULT_SCHEMA_PATH
    return _normalize(_parse_file(p), source=str(p))


def to_container_json(schema: dict[str, Any]) -> str:
    """Serialize a normalized schema for injection into the task container."""
    return json.dumps(schema)


def type_field(schema: dict[str, Any]) -> str | None:
    """Name of the first enum field, treated as the message 'type'/kind."""
    for f in schema["fields"]:
        if f.get("enum"):
            return str(f["name"])
    return None
