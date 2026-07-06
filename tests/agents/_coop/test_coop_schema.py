"""Tests for the structured-messaging schema loader (host-side)."""

import json

import pytest

from cooperbench.agents._coop import SchemaError, load_schema, to_container_json, type_field


class TestLoadSchema:
    def test_default_schema_loads(self):
        s = load_schema(None)
        assert s["name"] == "semi_structured_v1"
        names = [f["name"] for f in s["fields"]]
        assert "type" in names and "files" in names and "summary" in names
        assert type_field(s) == "type"  # first enum field is the 'kind'

    def test_load_json(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"name": "j", "fields": [{"name": "a", "required": True}]}))
        s = load_schema(p)
        assert s["name"] == "j"
        assert s["fields"][0]["required"] is True
        assert s["fields"][0]["enum"] is None

    def test_load_toml_with_enum(self, tmp_path):
        p = tmp_path / "s.toml"
        p.write_text('name = "t"\n[[field]]\nname = "a"\nrequired = true\nenum = ["X", "Y"]\n')
        s = load_schema(p)
        assert s["fields"][0]["enum"] == ["X", "Y"]

    def test_to_container_json_roundtrips(self):
        s = load_schema(None)
        assert json.loads(to_container_json(s)) == s

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(SchemaError):
            load_schema(tmp_path / "nope.toml")

    def test_no_name_rejected(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"fields": [{"name": "a"}]}))
        with pytest.raises(SchemaError):
            load_schema(p)

    def test_no_fields_rejected(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"name": "x", "fields": []}))
        with pytest.raises(SchemaError):
            load_schema(p)

    def test_bad_field_name_rejected(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"name": "x", "fields": [{"name": "has space"}]}))
        with pytest.raises(SchemaError):
            load_schema(p)

    def test_duplicate_field_rejected(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"name": "x", "fields": [{"name": "a"}, {"name": "a"}]}))
        with pytest.raises(SchemaError):
            load_schema(p)

    def test_enum_must_be_list_of_str(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"name": "x", "fields": [{"name": "a", "enum": [1, 2]}]}))
        with pytest.raises(SchemaError):
            load_schema(p)

    def test_malformed_toml_rejected(self, tmp_path):
        p = tmp_path / "s.toml"
        p.write_text("name = = broken")
        with pytest.raises(SchemaError):
            load_schema(p)

    def test_instructions_parsed(self, tmp_path):
        p = tmp_path / "s.toml"
        p.write_text(
            'name = "p"\ninstructions = "plan before code"\n[[field]]\nname = "type"\nrequired = true\nenum = ["A", "B"]\n'
        )
        s = load_schema(p)
        assert s["instructions"] == "plan before code"

    def test_instructions_default_none(self):
        assert load_schema(None)["instructions"] is None  # semi_structured_v1 has none

    def test_instructions_must_be_string(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text(json.dumps({"name": "x", "instructions": 5, "fields": [{"name": "a"}]}))
        with pytest.raises(SchemaError):
            load_schema(p)
