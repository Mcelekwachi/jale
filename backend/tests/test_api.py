from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from db_test_utils import db_connection

pytestmark = pytest.mark.asyncio
REPO_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def committed_dutch_translations(
    database_url: str, rows: list[tuple[int, str, str | None, str | None]]
) -> Iterator[None]:
    """Expose temporary translations to the API pool, then remove only those rows."""
    content_ids = [row[0] for row in rows]
    with db_connection(database_url) as conn:
        dutch_id = conn.execute("SELECT id FROM languages WHERE code = 'nld'").fetchone()[0]
        try:
            for content_id, translation, literal_translation, cultural_note in rows:
                conn.execute(
                    """
                    INSERT INTO content_translations
                        (content_id, meta_language_id, translation,
                         literal_translation, cultural_note)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        content_id,
                        dutch_id,
                        translation,
                        literal_translation,
                        cultural_note,
                    ),
                )
            yield
        finally:
            conn.execute(
                """
                DELETE FROM content_translations
                 WHERE meta_language_id = %s AND content_id = ANY(%s)
                """,
                (dutch_id, content_ids),
            )


def select_content_rows(
    database_url: str, selector: str = "TRUE", expected_count: int = 1
) -> list[tuple]:
    with db_connection(database_url) as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.target_text, ct.translation,
                   ct.literal_translation, ct.cultural_note
              FROM content_items c
              JOIN content_translations ct ON ct.content_id = c.id
              JOIN languages ml ON ml.id = ct.meta_language_id AND ml.code = 'eng'
             WHERE c.status = 'published' AND {selector}
             ORDER BY c.sort_order, c.id
             LIMIT %s
            """,
            (expected_count,),
        ).fetchall()
    assert len(rows) == expected_count, (
        f"selector {selector!r} returned {len(rows)} seeded rows; " f"expected {expected_count}"
    )
    return rows


def select_content_row(database_url: str, selector: str = "TRUE") -> tuple:
    return select_content_rows(database_url, selector)[0]


def assert_well_formed_quiz_options(item: dict) -> None:
    options = item["options"]
    assert len(options) == 4
    assert len({option["text"] for option in options}) == 4, "duplicate options"
    correct = [option for option in options if option["is_correct"]]
    assert len(correct) == 1
    assert correct[0]["text"] == item["answer"]


async def unit_items_path(client, track_slug: str, unit_title: str) -> str:
    response = await client.get(f"/v1/tracks/{track_slug}")
    assert response.status_code == 200
    unit = next(unit for unit in response.json()["units"] if unit["title"] == unit_title)
    return f"/v1/tracks/{track_slug}/units/{unit['position']}/items"


# --- health -----------------------------------------------------------------


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_health_db_reports_seeded_content(client):
    r = await client.get("/health/db")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["content_items"] == 211
    assert body["tracks"] == 6
    assert body["learnable_languages"] == 1
    assert "active_languages" not in body


# --- languages and categories ----------------------------------------------


async def test_active_languages(client):
    r = await client.get("/v1/languages")
    assert r.status_code == 200
    codes = [x["code"] for x in r.json()]
    assert codes == ["ibo"]


async def test_meta_language_coverage_reports_seeded_dutch_words_and_phrases(client):
    r = await client.get("/v1/languages/meta")
    assert r.status_code == 200
    languages = {language["code"]: language for language in r.json()}
    assert set(languages) == {"eng", "nld"}
    assert languages["eng"]["is_active"] is True
    assert languages["eng"]["translated_count"] == 211
    assert languages["eng"]["total_count"] == 211
    assert languages["nld"]["is_active"] is True
    assert languages["nld"]["translated_count"] == 107
    assert languages["nld"]["total_count"] == 211


async def test_language_catalogue_returns_roadmap_and_coverage_without_authentication(client):
    response = await client.get("/v1/languages/catalogue")

    assert response.status_code == 200
    catalogue = response.json()
    assert len(catalogue["learnable"]) == 5
    assert len(catalogue["meta"]) == 6
    learnable = {language["code"]: language for language in catalogue["learnable"]}
    meta = {language["code"]: language for language in catalogue["meta"]}
    assert learnable["ibo"]["available"] is True
    assert learnable["ibo"]["content_count"] == 211
    assert learnable["ibo"]["endonym"] == "Asụsụ Igbo"
    assert learnable["yor"]["available"] is False
    assert learnable["yor"]["content_count"] == 0
    assert meta["nld"]["available"] is True
    assert meta["nld"]["translated_count"] == 107
    assert meta["nld"]["total_count"] == 211


async def test_existing_language_endpoints_keep_their_shapes(client):
    learnable = await client.get("/v1/languages")
    meta = await client.get("/v1/languages/meta")

    assert set(learnable.json()[0]) == {"code", "name", "endonym", "flag_emoji", "is_active"}
    assert set(meta.json()[0]) == {
        "code",
        "name",
        "endonym",
        "flag_emoji",
        "is_active",
        "translated_count",
        "total_count",
    }


async def test_reseeding_catalogue_is_idempotent_and_language_file_wins(
    database_url,
):
    env = {**os.environ, "DATABASE_URL": database_url}
    command = [sys.executable, str(REPO_ROOT / "db" / "seed" / "seed.py"), "--all"]

    first = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    second = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True, text=True)

    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    with db_connection(database_url) as conn:
        rows = conn.execute("SELECT code, is_active FROM languages ORDER BY code").fetchall()
    assert len(rows) == 11
    assert len({row[0] for row in rows}) == 11
    assert dict(rows)["ibo"] is True


async def test_categories_exclude_empty_ones(client):
    r = await client.get("/v1/languages/ibo/categories")
    assert r.status_code == 200
    cats = r.json()
    assert all(c["item_count"] > 0 for c in cats)
    slugs = {c["slug"] for c in cats}
    assert "greetings" in slugs and "proverbs_unity" in slugs


async def test_unknown_language_is_404(client):
    r = await client.get("/v1/languages/zzz/categories")
    assert r.status_code == 404


# --- content ----------------------------------------------------------------


async def test_content_totals_by_type(client):
    expected = {"word": 111, "phrase": 50, "proverb": 50}
    for content_type, count in expected.items():
        r = await client.get(
            "/v1/content", params={"language": "ibo", "content_type": content_type}
        )
        assert r.status_code == 200
        assert r.json()["total"] == count


async def test_content_paging(client):
    r = await client.get("/v1/content", params={"language": "ibo", "limit": 10, "offset": 0})
    first = r.json()
    assert len(first["items"]) == 10
    assert first["total"] == 211

    r = await client.get("/v1/content", params={"language": "ibo", "limit": 10, "offset": 10})
    second = r.json()
    assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})


async def test_search_matches_igbo_and_english(client):
    r = await client.get("/v1/content", params={"language": "ibo", "q": "mother"})
    items = r.json()["items"]
    assert any(i["translation"].lower().startswith("mother") for i in items)
    assert all(i["meta_language"] == "eng" for i in items)

    r = await client.get("/v1/content", params={"language": "ibo", "q": "Ndewo"})
    assert r.json()["total"] >= 2  # exists as both a word and a phrase


@pytest.mark.parametrize("meta_language", ["zzz", "ibo"])
async def test_invalid_meta_language_is_rejected_by_all_endpoint_families(client, meta_language):
    listed = await client.get("/v1/content", params={"limit": 1})
    item_id = listed.json()["items"][0]["id"]
    endpoints = [
        ("/v1/content", {"meta_language": meta_language}),
        (f"/v1/content/{item_id}", {"meta_language": meta_language}),
        (
            "/v1/tracks/ibo_foundations/units/1/items",
            {"meta_language": meta_language},
        ),
    ]
    for path, params in endpoints:
        r = await client.get(path, params=params)
        assert r.status_code == 400, (path, r.text)


async def test_dutch_seed_falls_back_to_english_per_row(client):
    r = await client.get(
        "/v1/content", params={"language": "ibo", "meta_language": "nld", "limit": 200}
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert all(item["meta_language"] == "nld" for item in items)
    word = next(item for item in items if item["content_type"] == "word")
    proverb = next(item for item in items if item["content_type"] == "proverb")
    assert word["meta_language_used"] == "nld"
    assert proverb["meta_language_used"] == "eng"
    assert all(item["translation"] for item in items)


async def test_seeded_dutch_translations_produce_a_mixed_page(client):
    response = await client.get(
        "/v1/content",
        params={"language": "ibo", "meta_language": "nld", "limit": 200},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert sum(item["meta_language_used"] == "nld" for item in items) == 107
    assert sum(item["meta_language_used"] == "eng" for item in items) == 93


async def test_requested_translation_falls_back_each_optional_field_independently(
    client, database_url
):
    proverbs = select_content_rows(
        database_url,
        "c.content_type = 'proverb' AND ct.literal_translation IS NOT NULL "
        "AND ct.cultural_note IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM content_translations nld_ct "
        "JOIN languages nld ON nld.id = nld_ct.meta_language_id "
        "WHERE nld_ct.content_id = c.id AND nld.code = 'nld'"
        ")",
        expected_count=2,
    )
    dutch_literal = "Nederlandse letterlijke vertaling"
    dutch_cultural = "Nederlandse culturele uitleg"
    with committed_dutch_translations(
        database_url,
        [
            (proverbs[0][0], "Nederlands spreekwoord één", dutch_literal, None),
            (proverbs[1][0], "Nederlands spreekwoord twee", None, dutch_cultural),
        ],
    ):
        literal_authored = await client.get(
            f"/v1/content/{proverbs[0][0]}", params={"meta_language": "nld"}
        )
        cultural_authored = await client.get(
            f"/v1/content/{proverbs[1][0]}", params={"meta_language": "nld"}
        )
        assert literal_authored.status_code == cultural_authored.status_code == 200

        literal_item = literal_authored.json()
        assert literal_item["translation"] == "Nederlands spreekwoord één"
        assert literal_item["meta_language"] == "nld"
        assert literal_item["meta_language_used"] == "nld"
        assert literal_item["literal_translation"] == dutch_literal
        assert literal_item["cultural_note"] == proverbs[0][4]

        cultural_item = cultural_authored.json()
        assert cultural_item["translation"] == "Nederlands spreekwoord twee"
        assert cultural_item["meta_language"] == "nld"
        assert cultural_item["meta_language_used"] == "nld"
        assert cultural_item["literal_translation"] == proverbs[1][3]
        assert cultural_item["cultural_note"] == dutch_cultural


async def test_search_uses_the_resolved_dutch_translation(client, database_url):
    ndewo = select_content_row(database_url, "c.target_text = 'Ndewo'")
    r = await client.get(
        "/v1/content", params={"language": "ibo", "meta_language": "nld", "q": "Hallo"}
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(
        item["id"] == ndewo[0]
        and item["target_text"] == "Ndewo"
        and item["translation"] == "Hallo"
        and item["meta_language_used"] == "nld"
        for item in items
    )


# --- database invariants ----------------------------------------------------


async def test_seeded_translation_counts(database_url):
    with db_connection(database_url) as conn:
        rows = conn.execute(
            """
            SELECT l.code, count(ct.content_id)
              FROM languages l
              LEFT JOIN content_translations ct ON ct.meta_language_id = l.id
             WHERE l.code IN ('eng', 'nld')
             GROUP BY l.code
            """
        ).fetchall()

    assert dict(rows) == {"eng": 211, "nld": 107}


async def test_meta_language_coverage_counts_only_published_content(client, database_url):
    published = select_content_row(
        database_url,
        "c.content_type = 'proverb' AND NOT EXISTS ("
        "SELECT 1 FROM content_translations nld_ct "
        "JOIN languages nld ON nld.id = nld_ct.meta_language_id "
        "WHERE nld_ct.content_id = c.id AND nld.code = 'nld'"
        ")",
    )
    draft_key = f"test:draft:{uuid.uuid4()}"
    with db_connection(database_url) as conn:
        dutch_id = conn.execute("SELECT id FROM languages WHERE code = 'nld'").fetchone()[0]
        igbo_id = conn.execute("SELECT id FROM languages WHERE code = 'ibo'").fetchone()[0]
        draft_id = None
        try:
            conn.execute(
                """
                INSERT INTO content_translations
                    (content_id, meta_language_id, translation)
                VALUES (%s, %s, 'Tijdelijke gepubliceerde vertaling')
                """,
                (published[0], dutch_id),
            )
            draft_id = conn.execute(
                """
                INSERT INTO content_items
                    (source_key, language_id, content_type, target_text, status)
                VALUES (%s, %s, 'word', %s, 'draft')
                RETURNING id
                """,
                (draft_key, igbo_id, draft_key),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO content_translations
                    (content_id, meta_language_id, translation)
                VALUES (%s, %s, 'Ongepubliceerde vertaling')
                """,
                (draft_id, dutch_id),
            )

            r = await client.get("/v1/languages/meta")
            assert r.status_code == 200
            dutch = next(row for row in r.json() if row["code"] == "nld")
            assert dutch["translated_count"] == 108
            assert dutch["total_count"] == 211
        finally:
            if draft_id is not None:
                conn.execute("DELETE FROM content_items WHERE id = %s", (draft_id,))
            conn.execute(
                """
                DELETE FROM content_translations
                 WHERE content_id = %s AND meta_language_id = %s
                """,
                (published[0], dutch_id),
            )


async def test_meta_language_coverage_ignores_empty_translation_rows(client, database_url):
    untranslated = select_content_row(
        database_url,
        "NOT EXISTS ("
        "SELECT 1 FROM content_translations nld_ct "
        "JOIN languages nld ON nld.id = nld_ct.meta_language_id "
        "WHERE nld_ct.content_id = c.id AND nld.code = 'nld'"
        ")",
    )
    baseline_response = await client.get("/v1/languages/meta")
    assert baseline_response.status_code == 200
    baseline = next(row for row in baseline_response.json() if row["code"] == "nld")

    with db_connection(database_url) as conn:
        dutch_id = conn.execute("SELECT id FROM languages WHERE code = 'nld'").fetchone()[0]
        try:
            conn.execute(
                """
                INSERT INTO content_translations
                    (content_id, meta_language_id, translation)
                VALUES (%s, %s, '')
                """,
                (untranslated[0], dutch_id),
            )

            response = await client.get("/v1/languages/meta")
            assert response.status_code == 200
            dutch = next(row for row in response.json() if row["code"] == "nld")
            assert dutch["translated_count"] == baseline["translated_count"]
            assert dutch["total_count"] == baseline["total_count"]
        finally:
            conn.execute(
                """
                DELETE FROM content_translations
                 WHERE content_id = %s AND meta_language_id = %s
                """,
                (untranslated[0], dutch_id),
            )


async def test_meta_language_coverage_excludes_meta_only_target_content(client, database_url):
    unique_key = f"test:meta-target:{uuid.uuid4()}"
    baseline_response = await client.get("/v1/languages/meta")
    assert baseline_response.status_code == 200
    baseline = next(row for row in baseline_response.json() if row["code"] == "eng")

    with db_connection(database_url) as conn:
        english = conn.execute(
            "SELECT id, is_learnable, is_meta FROM languages WHERE code = 'eng'"
        ).fetchone()
        assert english[1:] == (False, True)
        english_id = english[0]
        content_id = None
        try:
            content_id = conn.execute(
                """
                INSERT INTO content_items
                    (source_key, language_id, content_type, target_text, status)
                VALUES (%s, %s, 'word', %s, 'published')
                RETURNING id
                """,
                (unique_key, english_id, unique_key),
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO content_translations
                    (content_id, meta_language_id, translation)
                VALUES (%s, %s, 'Temporary English translation')
                """,
                (content_id, english_id),
            )

            response = await client.get("/v1/languages/meta")
            assert response.status_code == 200
            english = next(row for row in response.json() if row["code"] == "eng")
            assert english["translated_count"] == baseline["translated_count"]
            assert english["total_count"] == baseline["total_count"]
        finally:
            if content_id is not None:
                conn.execute("DELETE FROM content_items WHERE id = %s", (content_id,))


async def test_english_proverb_translation_requires_a_cultural_note(database_url):
    unique_key = f"test:proverb:{uuid.uuid4()}"
    with db_connection(database_url, autocommit=False) as conn:
        try:
            content_id = conn.execute(
                """
                INSERT INTO content_items (source_key, language_id, content_type, target_text)
                SELECT %s, id, 'proverb', %s
                  FROM languages
                 WHERE code = 'ibo'
                RETURNING id
                """,
                (unique_key, unique_key),
            ).fetchone()[0]
            english_id = conn.execute("SELECT id FROM languages WHERE code = 'eng'").fetchone()[0]

            with pytest.raises(psycopg.errors.RaiseException, match=r"(?i)cultural.note"):
                conn.execute(
                    """
                    INSERT INTO content_translations
                        (content_id, meta_language_id, translation, cultural_note)
                    VALUES (%s, %s, %s, NULL)
                    """,
                    (content_id, english_id, "Test English translation"),
                )
        finally:
            conn.rollback()


async def test_open_flags_are_unique_per_item_and_translation_scope(database_url):
    user_id = uuid.uuid4()
    with db_connection(database_url, autocommit=False) as conn:
        try:
            conn.execute(
                "INSERT INTO app_users (id, email) VALUES (%s, %s)",
                (user_id, f"{user_id}@example.test"),
            )
            content_id = conn.execute(
                "SELECT id FROM content_items ORDER BY id LIMIT 1"
            ).fetchone()[0]
            english_id = conn.execute("SELECT id FROM languages WHERE code = 'eng'").fetchone()[0]

            conn.execute(
                """
                INSERT INTO content_flags (content_id, user_id, meta_language_id, reason)
                VALUES (%s, %s, NULL, 'other'), (%s, %s, %s, 'wrong_translation')
                """,
                (content_id, user_id, content_id, user_id, english_id),
            )
            count = conn.execute(
                "SELECT count(*) FROM content_flags WHERE content_id = %s AND user_id = %s",
                (content_id, user_id),
            ).fetchone()[0]
            assert count == 2

            for meta_language_id in (None, english_id):
                with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
                    conn.execute(
                        """
                        INSERT INTO content_flags
                            (content_id, user_id, meta_language_id, reason)
                        VALUES (%s, %s, %s, 'other')
                        """,
                        (content_id, user_id, meta_language_id),
                    )
        finally:
            conn.rollback()


async def test_duplicate_text_across_content_types_is_preserved(client):
    """Ndewo is deliberately both a word and a phrase — different study modes."""
    r = await client.get("/v1/content", params={"language": "ibo", "q": "Ndewo"})
    types = {i["content_type"] for i in r.json()["items"] if i["target_text"] == "Ndewo"}
    assert types == {"word", "phrase"}


async def test_every_proverb_carries_its_cultural_lesson(client):
    r = await client.get(
        "/v1/content", params={"language": "ibo", "content_type": "proverb", "limit": 200}
    )
    items = r.json()["items"]
    assert len(items) == 50
    assert all(i["cultural_note"] for i in items)


async def test_tone_policy_words_are_untoned(client):
    r = await client.get(
        "/v1/content", params={"language": "ibo", "content_type": "word", "limit": 200}
    )
    assert all(i["target_text_toned"] is None for i in r.json()["items"])


async def test_content_detail_and_404(client):
    listed = (await client.get("/v1/content", params={"language": "ibo", "limit": 1})).json()
    item_id = listed["items"][0]["id"]
    r = await client.get(f"/v1/content/{item_id}")
    assert r.status_code == 200
    assert r.json()["id"] == item_id
    assert (await client.get("/v1/content/99999999")).status_code == 404


# --- track resolution -------------------------------------------------------

PERSONAS = [
    ({"age": "child_u13", "connection": "complete_beginner"}, "ibo_child_play"),
    ({"connection": "complete_beginner"}, "ibo_foundations"),
    ({"connection": "language_enthusiast"}, "ibo_enthusiast_discovery"),
    ({"connection": "connected_to_igbo_family"}, "ibo_diaspora_culture"),
    ({"connection": "igbo_heritage_speaker"}, "ibo_heritage_structured"),
    ({"connection": "igbo_parent_abroad"}, "ibo_diaspora_culture"),
    ({"connection": "mixed_parent_abroad"}, "ibo_diaspora_culture"),
    ({"connection": "aboriginal_native"}, "ibo_native_advanced"),
    ({"connection": "other_african_heritage"}, "ibo_foundations"),
    ({"goal": "improve_proverbs_vocab"}, "ibo_native_advanced"),
]


@pytest.mark.parametrize("params,expected", PERSONAS)
async def test_every_persona_resolves(client, params, expected):
    r = await client.get("/v1/tracks/resolve", params={"language": "ibo", **params})
    assert r.status_code == 200
    assert r.json()["track"]["slug"] == expected


async def test_skipped_onboarding_still_resolves(client):
    """Onboarding is skippable at every screen — no user can be left without
    a curriculum."""
    r = await client.get("/v1/tracks/resolve")
    assert r.status_code == 200
    body = r.json()
    assert body["track"]["slug"] == "ibo_foundations"
    assert body["is_fallback"] is True


async def test_native_speaker_skips_beginner_content(client):
    r = await client.get("/v1/tracks/resolve", params={"connection": "aboriginal_native"})
    track = r.json()["track"]
    assert track["min_difficulty"] == "advanced"
    assert all(u["available"] > 0 for u in track["units"])


async def test_invalid_enum_value_is_rejected(client):
    r = await client.get("/v1/tracks/resolve", params={"connection": "martian"})
    assert r.status_code == 422


async def test_every_track_unit_has_content(client):
    tracks = (await client.get("/v1/tracks", params={"language": "ibo"})).json()
    assert len(tracks) == 6
    for t in tracks:
        detail = (await client.get(f"/v1/tracks/{t['slug']}")).json()
        assert detail["units"], f"{t['slug']} has no units"
        for u in detail["units"]:
            assert u["available"] > 0, f"{t['slug']} unit {u['position']} is empty"


# --- study sessions ---------------------------------------------------------


async def test_flashcard_session_shape(client):
    path = await unit_items_path(client, "ibo_foundations", "Greetings & Courtesy")
    r = await client.get(path)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "flashcard"
    assert len(body["items"]) == 9
    item = body["items"][0]
    assert item["prompt"] and item["answer"]
    assert item["options"] is None


async def test_study_direction_defaults_to_target_then_swaps_prompt_and_answer(
    client, database_url
):
    path = await unit_items_path(client, "ibo_foundations", "Greetings & Courtesy")
    params = {"meta_language": "nld", "shuffle_seed": 17}
    default = await client.get(path, params=params)
    reverse = await client.get(
        path,
        params={**params, "direction": "meta_to_target"},
    )
    assert default.status_code == reverse.status_code == 200
    default_items = {item["id"]: item for item in default.json()["items"]}
    reverse_items = {item["id"]: item for item in reverse.json()["items"]}
    assert default_items, "default direction returned no study items"
    assert default_items.keys() == reverse_items.keys()
    with db_connection(database_url) as conn:
        seeded = {
            row[0]: {"target_text": row[1], "translation": row[2]}
            for row in conn.execute(
                """
                SELECT c.id, c.target_text, ct.translation
                  FROM content_items c
                  JOIN content_translations ct ON ct.content_id = c.id
                  JOIN languages ml
                    ON ml.id = ct.meta_language_id AND ml.code = 'nld'
                 WHERE c.id = ANY(%s)
                """,
                (list(default_items),),
            )
        }
    assert seeded.keys() == default_items.keys()
    for item_id, item in default_items.items():
        assert item["meta_language"] == "nld"
        assert item["meta_language_used"] == "nld"
        assert item["prompt"] == seeded[item_id]["target_text"]
        assert item["answer"] == seeded[item_id]["translation"]
        assert reverse_items[item_id]["prompt"] == seeded[item_id]["translation"]
        assert reverse_items[item_id]["answer"] == seeded[item_id]["target_text"]


async def test_quiz_session_has_four_distinct_options_with_one_correct(client):
    path = await unit_items_path(client, "ibo_foundations", "Greetings Quiz")
    r = await client.get(path, params={"shuffle_seed": 7})
    body = r.json()
    assert body["mode"] == "quiz"
    for item in body["items"]:
        assert_well_formed_quiz_options(item)


async def test_quiz_options_follow_answer_side_for_seeded_dutch(client, database_url):
    path = await unit_items_path(client, "ibo_foundations", "Greetings Quiz")
    with db_connection(database_url) as conn:
        dutch_texts = {
            row[0]
            for row in conn.execute(
                """
                SELECT ct.translation
                  FROM content_translations ct
                  JOIN languages ml ON ml.id = ct.meta_language_id
                 WHERE ml.code = 'nld'
                """
            )
        }
        target_texts = {
            row[0]
            for row in conn.execute(
                "SELECT target_text FROM content_items WHERE status = 'published'"
            )
        }

    translated = await client.get(
        path,
        params={
            "meta_language": "nld",
            "direction": "target_to_meta",
            "shuffle_seed": 7,
        },
    )
    target = await client.get(
        path,
        params={
            "meta_language": "nld",
            "direction": "meta_to_target",
            "shuffle_seed": 7,
        },
    )
    assert translated.status_code == target.status_code == 200

    translated_items = {item["id"]: item for item in translated.json()["items"]}
    target_items = {item["id"]: item for item in target.json()["items"]}
    assert translated_items, "translated-answer quiz returned no items"
    assert translated_items.keys() == target_items.keys()
    assert all(item["meta_language_used"] == "nld" for item in translated_items.values())

    for item in translated_items.values():
        assert_well_formed_quiz_options(item)
        assert {option["text"] for option in item["options"]} <= dutch_texts

    for item in target_items.values():
        assert_well_formed_quiz_options(item)
        assert {option["text"] for option in item["options"]} <= target_texts


async def test_proverb_session_returns_the_cultural_lesson(client):
    r = await client.get("/v1/tracks/ibo_native_advanced/units/1/items")
    body = r.json()
    assert body["mode"] == "proverbs"
    assert body["items"], "native track opens with no proverbs"
    for item in body["items"]:
        assert item["cultural_note"], "proverb mode must carry the deeper lesson"


async def test_phrase_practice_session(client):
    path = await unit_items_path(client, "ibo_foundations", "Your First Phrases")
    r = await client.get(path)
    body = r.json()
    assert body["mode"] == "phrase_practice"
    assert all(i["content_type"] == "phrase" for i in body["items"])


async def test_shuffle_seed_is_reproducible(client):
    path = await unit_items_path(client, "ibo_foundations", "Alphabet")
    a = await client.get(path, params={"shuffle_seed": 42})
    b = await client.get(path, params={"shuffle_seed": 42})
    assert [i["id"] for i in a.json()["items"]] == [i["id"] for i in b.json()["items"]]


async def test_quiz_shuffle_seed_reproduces_item_and_option_order(client):
    path = await unit_items_path(client, "ibo_foundations", "Greetings Quiz")
    params = {
        "meta_language": "nld",
        "direction": "target_to_meta",
        "shuffle_seed": 42,
    }
    first = await client.get(path, params=params)
    second = await client.get(path, params=params)
    assert first.status_code == second.status_code == 200

    first_items = first.json()["items"]
    second_items = second.json()["items"]
    assert first_items, "seeded quiz returned no items"
    assert [item["id"] for item in first_items] == [item["id"] for item in second_items]
    assert [item["options"] for item in first_items] == [item["options"] for item in second_items]


async def test_unknown_unit_is_404(client):
    assert (await client.get("/v1/tracks/ibo_foundations/units/99/items")).status_code == 404
    assert (await client.get("/v1/tracks/nope/units/1/items")).status_code == 404


async def test_every_item_has_a_flag_target_and_audio_field(client):
    """Flag button and audio button ship with the first mode, not later."""
    path = await unit_items_path(client, "ibo_foundations", "Alphabet")
    r = await client.get(path)
    for item in r.json()["items"]:
        assert "id" in item and "flag_count" in item
        assert "audio_url" in item and "audio_state" in item
