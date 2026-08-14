from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from db_test_utils import db_connection

REPO_ROOT = Path(__file__).resolve().parents[2]


def create_user_and_contributor(database_url: str) -> tuple[uuid.UUID, int]:
    user_id = uuid.uuid4()
    with db_connection(database_url) as conn:
        conn.execute("INSERT INTO app_users (id) VALUES (%s)", (user_id,))
        contributor_id = conn.execute(
            "INSERT INTO contributors (user_id, display_name) VALUES (%s, 'Schema Test') "
            "RETURNING id",
            (user_id,),
        ).fetchone()[0]
    return user_id, contributor_id


def cleanup_user(database_url: str, user_id: uuid.UUID) -> None:
    with db_connection(database_url) as conn:
        contributor = conn.execute(
            "SELECT id FROM contributors WHERE user_id = %s", (user_id,)
        ).fetchone()
        if contributor:
            contributor_id = contributor[0]
            conn.execute("DELETE FROM earnings_ledger WHERE contributor_id = %s", (contributor_id,))
            conn.execute(
                "DELETE FROM validator_assignments WHERE validator_id = %s", (contributor_id,)
            )
            conn.execute(
                "DELETE FROM content_submissions WHERE contributor_id = %s", (contributor_id,)
            )
        conn.execute("DELETE FROM app_users WHERE id = %s", (user_id,))


def create_submission(database_url: str, contributor_id: int) -> int:
    with db_connection(database_url) as conn:
        language_id = conn.execute("SELECT id FROM languages WHERE code = 'ibo'").fetchone()[0]
        return conn.execute(
            """
            INSERT INTO content_submissions (
              contributor_id, language_id, submission_kind, content_type, target_text
            ) VALUES (%s, %s, 'new_content', 'word', %s)
            RETURNING id
            """,
            (contributor_id, language_id, f"schema-test-{uuid.uuid4()}"),
        ).fetchone()[0]


def test_contributor_requires_existing_unique_user(database_url):
    missing_user = uuid.uuid4()
    with (
        db_connection(database_url) as conn,
        pytest.raises(psycopg.errors.ForeignKeyViolation),
    ):
        conn.execute(
            "INSERT INTO contributors (user_id, display_name) VALUES (%s, 'Missing')",
            (missing_user,),
        )

    user_id, _ = create_user_and_contributor(database_url)
    try:
        with (
            db_connection(database_url) as conn,
            pytest.raises(psycopg.errors.UniqueViolation),
        ):
            conn.execute(
                "INSERT INTO contributors (user_id, display_name) VALUES (%s, 'Duplicate')",
                (user_id,),
            )
    finally:
        cleanup_user(database_url, user_id)


def test_validator_lifecycle_constraints(database_url):
    user_id, contributor_id = create_user_and_contributor(database_url)
    try:
        with db_connection(database_url) as conn:
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "UPDATE contributors SET validator_status = 'pending_verification', "
                    "validator_level = 'standard' WHERE id = %s",
                    (contributor_id,),
                )
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "UPDATE contributors SET validator_status = 'verified', "
                    "validator_verified_at = now() WHERE id = %s",
                    (contributor_id,),
                )
    finally:
        cleanup_user(database_url, user_id)


def test_submission_reference_constraints(database_url):
    user_id, contributor_id = create_user_and_contributor(database_url)
    try:
        with db_connection(database_url) as conn:
            language_id = conn.execute("SELECT id FROM languages WHERE code = 'ibo'").fetchone()[0]
            content_id = conn.execute(
                "SELECT id FROM content_items ORDER BY id LIMIT 1"
            ).fetchone()[0]
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO content_submissions (contributor_id, language_id, "
                    "submission_kind, content_type, target_text) "
                    "VALUES (%s, %s, 'correction', 'word', 'Correction')",
                    (contributor_id, language_id),
                )
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "INSERT INTO content_submissions (contributor_id, language_id, "
                    "submission_kind, content_type, target_text, corrects_content_id) "
                    "VALUES (%s, %s, 'new_content', 'word', 'New', %s)",
                    (contributor_id, language_id, content_id),
                )
    finally:
        cleanup_user(database_url, user_id)


def test_submission_proverb_note_trigger(database_url):
    user_id, contributor_id = create_user_and_contributor(database_url)
    try:
        with db_connection(database_url) as conn:
            language_id = conn.execute("SELECT id FROM languages WHERE code = 'ibo'").fetchone()[0]
            meta_id = conn.execute("SELECT id FROM languages WHERE code = 'eng'").fetchone()[0]
            with pytest.raises(psycopg.errors.RaiseException, match="cultural_note is required"):
                conn.execute(
                    "INSERT INTO content_submissions (contributor_id, language_id, "
                    "submission_kind, content_type, target_text, meta_language_id, translation) "
                    "VALUES (%s, %s, 'new_content', 'proverb', 'Test proverb', %s, 'Meaning')",
                    (contributor_id, language_id, meta_id),
                )
            conn.execute(
                "INSERT INTO content_submissions (contributor_id, language_id, submission_kind, "
                "content_type, target_text, meta_language_id, translation) "
                "VALUES (%s, %s, 'new_content', 'proverb', 'Untranslated proverb', %s, NULL)",
                (contributor_id, language_id, meta_id),
            )
    finally:
        cleanup_user(database_url, user_id)


def test_validator_assignment_constraints(database_url):
    submitter_user, submitter_id = create_user_and_contributor(database_url)
    validator_user, validator_id = create_user_and_contributor(database_url)
    try:
        submission_id = create_submission(database_url, submitter_id)
        with db_connection(database_url) as conn:
            conn.execute(
                "INSERT INTO validator_assignments (submission_id, validator_id) VALUES (%s, %s)",
                (submission_id, validator_id),
            )
            with pytest.raises(psycopg.errors.UniqueViolation):
                conn.execute(
                    "INSERT INTO validator_assignments (submission_id, validator_id) "
                    "VALUES (%s, %s)",
                    (submission_id, validator_id),
                )
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "UPDATE validator_assignments SET decided_at = now() WHERE submission_id = %s",
                    (submission_id,),
                )
            with pytest.raises(psycopg.errors.CheckViolation):
                conn.execute(
                    "UPDATE validator_assignments SET decision = 'approve' "
                    "WHERE submission_id = %s",
                    (submission_id,),
                )
    finally:
        cleanup_user(database_url, submitter_user)
        cleanup_user(database_url, validator_user)


def test_ledger_batch_reference_is_unique(database_url):
    user_id, contributor_id = create_user_and_contributor(database_url)
    try:
        batch = f"schema-test-{uuid.uuid4()}"
        with db_connection(database_url) as conn:
            conn.execute(
                "INSERT INTO earnings_ledger (contributor_id, role, batch_reference, item_count, "
                "rate_description, amount_eur_cents) "
                "VALUES (%s, 'contributor', %s, 1, '1 accepted word @ EUR 3.00', 300)",
                (contributor_id, batch),
            )
            with pytest.raises(psycopg.errors.UniqueViolation):
                conn.execute(
                    "INSERT INTO earnings_ledger (contributor_id, role, batch_reference, "
                    "item_count, rate_description, amount_eur_cents) "
                    "VALUES (%s, 'contributor', %s, 1, 'retry', 300)",
                    (contributor_id, batch),
                )
    finally:
        cleanup_user(database_url, user_id)


def test_required_validators_defaults_and_seeds(database_url):
    with db_connection(database_url) as conn:
        code = f"z{uuid.uuid4().hex[:2]}"
        row = conn.execute(
            "INSERT INTO languages (code, name) VALUES (%s, 'Threshold Test') "
            "RETURNING id, required_validators",
            (code,),
        ).fetchone()
        try:
            assert row[1] == 1
            assert (
                conn.execute(
                    "SELECT required_validators FROM languages WHERE code = 'ibo'"
                ).fetchone()[0]
                == 1
            )
        finally:
            conn.execute("DELETE FROM languages WHERE id = %s", (row[0],))


def test_seeding_twice_preserves_registry_and_row_counts(database_url):
    command = [sys.executable, str(REPO_ROOT / "db" / "seed" / "seed.py"), "--all"]
    env = {**os.environ, "DATABASE_URL": database_url}

    first = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    with db_connection(database_url) as conn:
        registry_after_first = conn.execute(
            "SELECT code, name, is_active, is_learnable, is_meta, required_validators, "
            "sort_order FROM languages ORDER BY code"
        ).fetchall()
        counts_after_first = conn.execute(
            "SELECT (SELECT count(*) FROM languages), (SELECT count(*) FROM categories), "
            "(SELECT count(*) FROM content_items), "
            "(SELECT count(*) FROM content_translations), (SELECT count(*) FROM tracks)"
        ).fetchone()

    second = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert second.returncode == 0, second.stdout + second.stderr
    with db_connection(database_url) as conn:
        registry_after_second = conn.execute(
            "SELECT code, name, is_active, is_learnable, is_meta, required_validators, "
            "sort_order FROM languages ORDER BY code"
        ).fetchall()
        counts_after_second = conn.execute(
            "SELECT (SELECT count(*) FROM languages), (SELECT count(*) FROM categories), "
            "(SELECT count(*) FROM content_items), "
            "(SELECT count(*) FROM content_translations), (SELECT count(*) FROM tracks)"
        ).fetchone()

    assert registry_after_second == registry_after_first
    assert counts_after_second == counts_after_first
