from __future__ import annotations

import uuid

import psycopg
import pytest

pytestmark = pytest.mark.asyncio


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
    assert body["content_items"] == 157
    assert body["tracks"] == 6


# --- languages and categories ----------------------------------------------


async def test_active_languages(client):
    r = await client.get("/v1/languages")
    assert r.status_code == 200
    codes = [x["code"] for x in r.json()]
    assert codes == ["ibo"]


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
    expected = {"word": 57, "phrase": 50, "proverb": 50}
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
    assert first["total"] == 157

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


# --- database invariants ----------------------------------------------------


async def test_seeded_translation_counts(database_url):
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT l.code, count(ct.content_id)
              FROM languages l
              LEFT JOIN content_translations ct ON ct.meta_language_id = l.id
             WHERE l.code IN ('eng', 'nld')
             GROUP BY l.code
            """
        ).fetchall()

    assert dict(rows) == {"eng": 157, "nld": 0}


async def test_proverb_translation_requires_a_cultural_note(database_url):
    unique_key = f"test:proverb:{uuid.uuid4()}"
    with psycopg.connect(database_url) as conn:
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
                    (content_id, english_id, "Test translation"),
                )
        finally:
            conn.rollback()


async def test_open_flags_are_unique_per_item_and_translation_scope(database_url):
    user_id = uuid.uuid4()
    with psycopg.connect(database_url) as conn:
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
    r = await client.get("/v1/tracks/ibo_foundations/units/1/items")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "flashcard"
    assert len(body["items"]) == 9
    item = body["items"][0]
    assert item["prompt"] and item["answer"]
    assert item["options"] is None


async def test_quiz_session_has_four_distinct_options_with_one_correct(client):
    r = await client.get("/v1/tracks/ibo_foundations/units/2/items", params={"shuffle_seed": 7})
    body = r.json()
    assert body["mode"] == "quiz"
    for item in body["items"]:
        opts = item["options"]
        assert len(opts) == 4
        assert len({o["text"] for o in opts}) == 4, "duplicate options"
        correct = [o for o in opts if o["is_correct"]]
        assert len(correct) == 1
        assert correct[0]["text"] == item["answer"]


async def test_proverb_session_returns_the_cultural_lesson(client):
    r = await client.get("/v1/tracks/ibo_native_advanced/units/1/items")
    body = r.json()
    assert body["mode"] == "proverbs"
    assert body["items"], "native track opens with no proverbs"
    for item in body["items"]:
        assert item["cultural_note"], "proverb mode must carry the deeper lesson"


async def test_phrase_practice_session(client):
    r = await client.get("/v1/tracks/ibo_foundations/units/3/items")
    body = r.json()
    assert body["mode"] == "phrase_practice"
    assert all(i["content_type"] == "phrase" for i in body["items"])


async def test_shuffle_seed_is_reproducible(client):
    a = await client.get("/v1/tracks/ibo_foundations/units/1/items", params={"shuffle_seed": 42})
    b = await client.get("/v1/tracks/ibo_foundations/units/1/items", params={"shuffle_seed": 42})
    assert [i["id"] for i in a.json()["items"]] == [i["id"] for i in b.json()["items"]]


async def test_unknown_unit_is_404(client):
    assert (await client.get("/v1/tracks/ibo_foundations/units/99/items")).status_code == 404
    assert (await client.get("/v1/tracks/nope/units/1/items")).status_code == 404


async def test_every_item_has_a_flag_target_and_audio_field(client):
    """Flag button and audio button ship with the first mode, not later."""
    r = await client.get("/v1/tracks/ibo_foundations/units/1/items")
    for item in r.json()["items"]:
        assert "id" in item and "flag_count" in item
        assert "audio_url" in item and "audio_state" in item
