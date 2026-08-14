from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "db" / "seed"))
import seed  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")


def enum_values(name: str) -> list[str]:
    match = re.search(rf"CREATE TYPE {name}\s+AS ENUM \((.*?)\);", SCHEMA, re.DOTALL)
    assert match, f"missing enum {name}"
    return re.findall(r"'([^']+)'", match.group(1))


def test_contributor_enums_publish_exact_values():
    assert enum_values("contributor_status") == ["active", "paused", "suspended"]
    assert enum_values("contributor_level") == ["learner", "speaker", "keeper", "elder"]
    assert enum_values("validator_status") == [
        "not_applicable",
        "pending_verification",
        "verified",
        "suspended",
    ]
    assert enum_values("validator_level") == ["standard", "senior"]
    assert enum_values("payment_provider") == ["paystack", "wise"]
    assert enum_values("submission_status") == ["pending", "in_review", "accepted", "rejected"]
    assert enum_values("validator_decision") == ["approve", "reject"]
    assert enum_values("earnings_role") == ["contributor", "validator"]
    assert enum_values("earnings_status") == ["pending", "paid", "failed"]
    assert enum_values("submission_kind") == [
        "new_content",
        "correction",
        "dialect_variant",
        "audio",
    ]


def test_user_role_includes_validator():
    assert enum_values("user_role") == ["learner", "contributor", "validator", "admin"]


def test_schema_declares_contributor_tables_and_threshold():
    for table in (
        "contributors",
        "content_submissions",
        "validator_assignments",
        "earnings_ledger",
    ):
        assert re.search(rf"CREATE TABLE(?: IF NOT EXISTS)? {table}\b", SCHEMA)
    assert "required_validators SMALLINT NOT NULL DEFAULT 1" in SCHEMA
    assert "english_translation" not in SCHEMA


def test_registry_defaults_required_validators_to_one():
    errors: list[str] = []
    registry, _ = seed.load_language_registry(errors)

    assert errors == []
    assert registry
    assert all(language["required_validators"] == 1 for language in registry)


def test_language_upsert_binds_required_validator_threshold():
    class Cursor:
        def execute(self, _query, params):
            self.params = params

        def fetchone(self):
            return {"id": 1}

    cursor = Cursor()
    seed.upsert_language(
        cursor,
        {
            "code": "ibo",
            "name": "Igbo",
            "required_validators": 3,
        },
    )

    assert cursor.params["required_validators"] == 3
