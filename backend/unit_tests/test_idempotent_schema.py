from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
ENTRYPOINT = (REPO_ROOT / "scripts" / "entrypoint.sh").read_text(encoding="utf-8")


def test_schema_create_statements_are_rerunnable():
    assert not re.search(r"^CREATE TABLE (?!IF NOT EXISTS)", SCHEMA, re.MULTILINE)
    assert not re.search(r"^CREATE (?:UNIQUE )?INDEX (?!IF NOT EXISTS)", SCHEMA, re.MULTILINE)
    assert not re.search(r"^CREATE TYPE ", SCHEMA, re.MULTILINE)
    assert "DROP VIEW IF EXISTS admin_flag_queue;\nCREATE VIEW admin_flag_queue AS" in SCHEMA


def test_every_trigger_is_dropped_before_creation():
    triggers = re.findall(r"^CREATE TRIGGER (\w+).*? ON (\w+)", SCHEMA, re.MULTILINE)
    assert triggers
    for trigger, table in triggers:
        assert f"DROP TRIGGER IF EXISTS {trigger} ON {table};" in SCHEMA


def test_every_table_has_an_add_column_upgrade_pass():
    tables = re.findall(r"^CREATE TABLE(?: IF NOT EXISTS)? (\w+) \(", SCHEMA, re.MULTILINE)
    assert tables
    for table in tables:
        assert re.search(
            rf"ALTER TABLE {table}\s+ADD COLUMN IF NOT EXISTS", SCHEMA
        ), f"{table} has no ADD COLUMN IF NOT EXISTS upgrade pass"


def test_enum_values_are_added_at_the_end_for_existing_types():
    marker = "-- ENUM VALUE UPGRADES — keep at the end of the file"
    assert marker in SCHEMA
    upgrades = SCHEMA.split(marker, maxsplit=1)[1]
    assert "ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'validator';" in upgrades
    assert "CREATE TABLE" not in upgrades


def test_entrypoint_always_applies_schema_and_propagates_failure():
    assert "to_regclass('public.content_items')" not in ENTRYPOINT
    assert "schema already present, skipping" not in ENTRYPOINT
    assert "entrypoint: applying db/schema.sql (idempotent)" in ENTRYPOINT
    assert "conn.execute(fh.read())" in ENTRYPOINT
    assert "set -euo pipefail" in ENTRYPOINT
