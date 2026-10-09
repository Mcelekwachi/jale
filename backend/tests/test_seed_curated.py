"""The seed must never overwrite text a person has verified or edited.

Production runs the seed on every boot, so without this guard an admin's
correction to an Igbo word would be reverted by the next deploy.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

from db_test_utils import db_connection

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_KEY_SQL = "SELECT id, target_text FROM content_items WHERE language_id = (SELECT id FROM languages WHERE code='ibo') ORDER BY id LIMIT %s"


def _reseed(database_url: str) -> str:
    import os

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "db" / "seed" / "seed.py"), "--language", "ibo"],
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _items(conn, count: int):
    return conn.execute(SEED_KEY_SQL, (count,)).fetchall()


def test_admin_edited_text_survives_reseed_and_seed_changes_are_logged(database_url):
    admin_id = uuid.uuid4()
    with db_connection(database_url) as conn:
        (edited_id, edited_text), (verified_id, verified_text), (plain_id, plain_text) = _items(
            conn, 3
        )
        conn.execute(
            "INSERT INTO app_users (id, email, role) VALUES (%s, %s, 'admin')",
            (admin_id, f"{admin_id}@example.test"),
        )
        try:
            # 1. admin edited through the API path: revision with an author
            conn.execute(
                "UPDATE content_items SET target_text = %s WHERE id = %s",
                ("ADMIN-CORRECTED", edited_id),
            )
            conn.execute(
                "INSERT INTO content_revisions (content_id, changed_by, change_note, before_state, after_state)"
                " VALUES (%s, %s, 'fix', '{}', '{}')",
                (edited_id, admin_id),
            )
            # 2. verified by a person, no text revision
            conn.execute(
                "UPDATE content_items SET target_text = %s, verified = TRUE, verified_by = %s,"
                " verified_at = now() WHERE id = %s",
                ("VERIFIED-TEXT", admin_id, verified_id),
            )
            # 3. untouched row drifted from the file: the file should win and be logged
            conn.execute(
                "UPDATE content_items SET target_text = %s WHERE id = %s",
                ("DRIFTED", plain_id),
            )

            output = _reseed(database_url)

            rows = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT id, target_text FROM content_items WHERE id = ANY(%s)",
                    ([edited_id, verified_id, plain_id],),
                )
            }
            assert rows[edited_id] == "ADMIN-CORRECTED"
            assert rows[verified_id] == "VERIFIED-TEXT"
            assert rows[plain_id] == plain_text  # restored from the file

            assert "KEPT" in output  # curated differences are reported, not applied

            seed_revisions = conn.execute(
                "SELECT before_state->>'target_text', after_state->>'target_text', changed_by"
                " FROM content_revisions WHERE content_id = %s",
                (plain_id,),
            ).fetchall()
            assert ("DRIFTED", plain_text, None) in seed_revisions
        finally:
            conn.execute(
                "DELETE FROM content_revisions WHERE content_id = ANY(%s)",
                ([edited_id, verified_id, plain_id],),
            )
            conn.execute(
                "UPDATE content_items SET target_text = %s, verified = FALSE, verified_by = NULL,"
                " verified_at = NULL WHERE id = %s",
                (verified_text, verified_id),
            )
            conn.execute(
                "UPDATE content_items SET target_text = %s WHERE id = %s", (edited_text, edited_id)
            )
            conn.execute("DELETE FROM app_users WHERE id = %s", (admin_id,))
