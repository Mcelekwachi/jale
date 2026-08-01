from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.asyncio


@contextmanager
def study_user(database_url: str, user_id: uuid.UUID) -> Iterator[None]:
    try:
        yield
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("DELETE FROM app_users WHERE id = %s", (user_id,))


def published_content_ids(database_url: str, count: int = 3) -> list[int]:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT id FROM content_items WHERE status = 'published' ORDER BY id LIMIT %s",
            (count,),
        ).fetchall()
    assert len(rows) == count
    return [row[0] for row in rows]


def answer(
    content_id: int,
    *,
    correct: bool,
    duration_ms: int | None = None,
    client_answer_id: uuid.UUID | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "content_id": content_id,
        "correct": correct,
        "mode": "flashcard",
    }
    if duration_ms is not None:
        value["duration_ms"] = duration_ms
    if client_answer_id is not None:
        value["client_answer_id"] = str(client_answer_id)
    return value


def progress_rows(database_url: str, user_id: uuid.UUID) -> dict[int, tuple]:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT content_id, times_seen, times_correct, times_incorrect,
                   leitner_box, due_at, mastered
              FROM user_progress
             WHERE user_id = %s
             ORDER BY content_id
            """,
            (user_id,),
        ).fetchall()
    return {row[0]: row[1:] for row in rows}


def activity_rows(database_url: str, user_id: uuid.UUID) -> list[tuple]:
    with psycopg.connect(database_url) as conn:
        return conn.execute(
            """
            SELECT activity_date, items_reviewed, seconds_spent, xp, goal_met
              FROM user_daily_activity
             WHERE user_id = %s
             ORDER BY activity_date
            """,
            (user_id,),
        ).fetchall()


@contextmanager
def fixed_utc_now(client, instant: datetime) -> Iterator[None]:
    from app.services.study_progress import get_utc_now

    app = client._transport.app
    missing = object()
    previous = app.dependency_overrides.get(get_utc_now, missing)
    app.dependency_overrides[get_utc_now] = lambda: instant
    try:
        yield
    finally:
        if previous is missing:
            app.dependency_overrides.pop(get_utc_now, None)
        else:
            app.dependency_overrides[get_utc_now] = previous


def drop_progress_trigger(database_url: str, trigger: str, function: str) -> None:
    try:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP TRIGGER IF EXISTS {} ON user_progress").format(
                    sql.Identifier(trigger)
                )
            )
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP FUNCTION IF EXISTS {}()").format(sql.Identifier(function)))


async def provision(client, headers: dict[str, str]) -> None:
    response = await client.get("/v1/me", headers=headers)
    assert response.status_code == 200


async def test_study_answers_requires_authentication_and_ignores_request_user_id(
    client, database_url, auth_headers
):
    owner_id, other_id = uuid.uuid4(), uuid.uuid4()
    content_id = published_content_ids(database_url, 1)[0]
    payload = {"answers": [answer(content_id, correct=True)]}

    unauthenticated = await client.post("/v1/study/answers", json=payload)
    assert unauthenticated.status_code == 401

    with study_user(database_url, owner_id), study_user(database_url, other_id):
        other_headers = auth_headers(subject=other_id)
        await provision(client, other_headers)
        response = await client.post(
            "/v1/study/answers",
            headers=auth_headers(subject=owner_id),
            params={"user_id": str(other_id)},
            json=payload,
        )

        assert response.status_code == 200
        assert set(progress_rows(database_url, owner_id)) == {content_id}
        assert progress_rows(database_url, other_id) == {}


async def test_batch_size_accepts_one_and_one_hundred_but_rejects_more_than_one_hundred(
    client, database_url, user_id, auth_headers
):
    content_id = published_content_ids(database_url, 1)[0]
    headers = auth_headers(subject=user_id)
    with study_user(database_url, user_id):
        one = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=True)]},
        )
        hundred = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=True) for _ in range(100)]},
        )
        too_many = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=True) for _ in range(101)]},
        )

    assert one.status_code == hundred.status_code == 200
    assert too_many.status_code == 422


async def test_empty_batch_is_a_read_only_no_op(client, database_url, user_id, auth_headers):
    instant = datetime(2026, 8, 1, 2, tzinfo=UTC)
    activity_date = datetime(2026, 8, 1).date()
    headers = auth_headers(subject=user_id)
    with fixed_utc_now(client, instant), study_user(database_url, user_id):
        await provision(client, headers)
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                """
                UPDATE user_stats
                   SET current_streak = 4, longest_streak = 7,
                       total_items_seen = 9, total_mastered = 2, total_xp = 80
                 WHERE user_id = %s
                """,
                (user_id,),
            )
            conn.execute(
                """
                INSERT INTO user_daily_activity
                    (user_id, activity_date, items_reviewed, seconds_spent, xp, goal_met)
                VALUES (%s, %s, 3, 90, 34, false)
                """,
                (user_id, activity_date),
            )

        before_activity = activity_rows(database_url, user_id)

        response = await client.post("/v1/study/answers", headers=headers, json={"answers": []})

        assert response.status_code == 200
        assert response.json()["results"] == []
        assert response.json()["accepted_count"] == 0
        assert response.json()["skipped_count"] == 0
        assert response.json()["current_streak"] == 4
        assert response.json()["today_xp"] == 34
        assert activity_rows(database_url, user_id) == before_activity
        with psycopg.connect(database_url) as conn:
            stats = conn.execute(
                """
                SELECT current_streak, longest_streak, total_items_seen,
                       total_mastered, total_xp
                  FROM user_stats WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
        assert stats == (4, 7, 9, 2, 80)


@pytest.mark.parametrize("missing_field", ["correct", "mode"])
async def test_each_answer_requires_correct_and_mode(
    client, database_url, user_id, auth_headers, missing_field
):
    item = answer(published_content_ids(database_url, 1)[0], correct=True)
    item.pop(missing_field)
    with study_user(database_url, user_id):
        response = await client.post(
            "/v1/study/answers",
            headers=auth_headers(subject=user_id),
            json={"answers": [item]},
        )
    assert response.status_code == 422


async def test_answer_rejects_unknown_study_mode(client, database_url, user_id, auth_headers):
    item = answer(published_content_ids(database_url, 1)[0], correct=True)
    item["mode"] = "speed_run"
    with study_user(database_url, user_id):
        response = await client.post(
            "/v1/study/answers",
            headers=auth_headers(subject=user_id),
            json={"answers": [item]},
        )
    assert response.status_code == 422


async def test_three_accepted_answers_update_progress_and_batch_totals_atomically(
    client, database_url, user_id, auth_headers
):
    ids = published_content_ids(database_url)
    client_ids = [uuid.uuid4() for _ in ids]
    submitted = [
        answer(ids[0], correct=True, duration_ms=1_500, client_answer_id=client_ids[0]),
        answer(ids[1], correct=False, duration_ms=None, client_answer_id=client_ids[1]),
        answer(ids[2], correct=True, duration_ms=2_499, client_answer_id=client_ids[2]),
    ]
    before = datetime.now(UTC)
    with study_user(database_url, user_id):
        response = await client.post(
            "/v1/study/answers",
            headers=auth_headers(subject=user_id),
            json={"answers": submitted},
        )
        after = datetime.now(UTC)
        rows = progress_rows(database_url, user_id)
        activity = activity_rows(database_url, user_id)

    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 3
    assert body["skipped_count"] == 0
    assert [(r["content_id"], r["client_answer_id"]) for r in body["results"]] == [
        (content_id, str(client_id)) for content_id, client_id in zip(ids, client_ids, strict=True)
    ]
    assert [r["status"] for r in body["results"]] == ["accepted"] * 3
    assert rows[ids[0]][:4] == (1, 1, 0, 1)
    assert rows[ids[1]][:4] == (1, 0, 1, 0)
    assert rows[ids[2]][:4] == (1, 1, 0, 1)
    assert all(row[5] is False for row in rows.values())
    assert before + timedelta(days=1) <= rows[ids[0]][4] <= after + timedelta(days=1)
    assert before + timedelta(minutes=10) <= rows[ids[1]][4] <= after + timedelta(minutes=10)
    assert before + timedelta(days=1) <= rows[ids[2]][4] <= after + timedelta(days=1)
    assert len(activity) == 1
    assert activity[0][1:] == (3, 3, 22, False)
    assert body["today_xp"] == 22


async def test_duration_is_optional_nullable_clamped_and_floored_once_per_batch(
    client, database_url, user_id, auth_headers
):
    ids = published_content_ids(database_url)
    submitted = [
        answer(ids[0], correct=True, duration_ms=-50),
        {**answer(ids[1], correct=False), "duration_ms": None},
        answer(ids[2], correct=True, duration_ms=301_500),
    ]
    with study_user(database_url, user_id):
        response = await client.post(
            "/v1/study/answers",
            headers=auth_headers(subject=user_id),
            json={"answers": submitted},
        )
        activity = activity_rows(database_url, user_id)

    assert response.status_code == 200
    assert activity[0][2] == 300


async def test_leitner_intervals_cap_at_five_and_incorrect_resets_to_zero(
    client, database_url, user_id, auth_headers
):
    content_id = published_content_ids(database_url, 1)[0]
    headers = auth_headers(subject=user_id)
    expected = [
        timedelta(days=1),
        timedelta(days=3),
        timedelta(days=7),
        timedelta(days=21),
        timedelta(days=60),
        timedelta(days=60),
    ]
    with study_user(database_url, user_id):
        for attempt, interval in enumerate(expected, start=1):
            before = datetime.now(UTC)
            response = await client.post(
                "/v1/study/answers",
                headers=headers,
                json={"answers": [answer(content_id, correct=True)]},
            )
            after = datetime.now(UTC)
            result = response.json()["results"][0]
            expected_box = min(attempt, 5)
            assert result["leitner_box"] == expected_box
            assert result["mastered"] is (expected_box == 5)
            due = datetime.fromisoformat(result["due_at"].replace("Z", "+00:00"))
            assert before + interval <= due <= after + interval

        before_incorrect = datetime.now(UTC)
        incorrect = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=False)]},
        )
        after_incorrect = datetime.now(UTC)
        stored = progress_rows(database_url, user_id)[content_id]
        with psycopg.connect(database_url) as conn:
            stats = conn.execute(
                """
                SELECT total_items_seen, total_mastered, total_xp
                  FROM user_stats WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()

    assert incorrect.status_code == 200
    assert incorrect.json()["results"][0]["leitner_box"] == 0
    assert incorrect.json()["results"][0]["mastered"] is False
    assert stored[:4] == (7, 6, 1, 0)
    assert stored[5] is False
    assert (
        before_incorrect + timedelta(minutes=10)
        <= stored[4]
        <= after_incorrect + timedelta(minutes=10)
    )
    assert stats == (1, 0, 62)


async def test_unknown_and_unpublished_content_are_reported_in_order_and_skipped(
    client, database_url, user_id, auth_headers
):
    published_id, unpublished_id = published_content_ids(database_url, 2)
    unknown_id = 9_223_372_036_854_775_000
    submitted_ids = [unknown_id, published_id, unpublished_id]
    with study_user(database_url, user_id):
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                "UPDATE content_items SET status = 'draft' WHERE id = %s", (unpublished_id,)
            )
        try:
            response = await client.post(
                "/v1/study/answers",
                headers=auth_headers(subject=user_id),
                json={"answers": [answer(value, correct=True) for value in submitted_ids]},
            )
            rows = progress_rows(database_url, user_id)
        finally:
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute(
                    "UPDATE content_items SET status = 'published' WHERE id = %s", (unpublished_id,)
                )

    assert response.status_code == 200
    body = response.json()
    assert [result["content_id"] for result in body["results"]] == submitted_ids
    assert all(result["client_answer_id"] is None for result in body["results"])
    assert [result["status"] for result in body["results"]] == [
        "unknown_content",
        "accepted",
        "unknown_content",
    ]
    assert body["accepted_count"] == 1
    assert body["skipped_count"] == 2
    assert set(rows) == {published_id}


async def test_idempotency_retry_conflict_and_within_batch_classification(
    client, database_url, user_id, auth_headers
):
    first_content, second_content = published_content_ids(database_url, 2)
    answer_id = uuid.uuid4()
    headers = auth_headers(subject=user_id)
    first = answer(first_content, correct=True, duration_ms=1_000, client_answer_id=answer_id)
    with study_user(database_url, user_id):
        accepted = await client.post(
            "/v1/study/answers", headers=headers, json={"answers": [first]}
        )
        advanced = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(first_content, correct=True)]},
        )
        duplicate = await client.post(
            "/v1/study/answers", headers=headers, json={"answers": [first]}
        )
        conflict = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={
                "answers": [
                    answer(
                        second_content, correct=False, duration_ms=2_000, client_answer_id=answer_id
                    )
                ]
            },
        )
        batch_id = uuid.uuid4()
        mixed = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={
                "answers": [
                    answer(second_content, correct=False, client_answer_id=batch_id),
                    answer(second_content, correct=True, client_answer_id=batch_id),
                    answer(first_content, correct=True, client_answer_id=batch_id),
                ]
            },
        )
        rows = progress_rows(database_url, user_id)
        activity = activity_rows(database_url, user_id)

    assert accepted.json()["results"][0]["status"] == "accepted"
    duplicate_result = duplicate.json()["results"][0]
    assert duplicate_result["status"] == "duplicate"
    for field in ("leitner_box", "due_at", "mastered"):
        assert duplicate_result[field] == advanced.json()["results"][0][field]
    assert duplicate_result["content_id"] == first_content
    assert duplicate_result["client_answer_id"] == str(answer_id)
    conflict_result = conflict.json()["results"][0]
    assert conflict_result["status"] == "id_conflict"
    assert conflict_result["leitner_box"] is None
    assert conflict_result["due_at"] is None
    assert conflict_result["mastered"] is False
    assert conflict_result["content_id"] == second_content
    assert conflict_result["client_answer_id"] == str(answer_id)
    assert [result["status"] for result in mixed.json()["results"]] == [
        "accepted",
        "duplicate",
        "id_conflict",
    ]
    assert [result["content_id"] for result in mixed.json()["results"]] == [
        second_content,
        second_content,
        first_content,
    ]
    assert [result["client_answer_id"] for result in mixed.json()["results"]] == [
        str(batch_id),
        str(batch_id),
        str(batch_id),
    ]
    assert rows[first_content][:4] == (2, 2, 0, 2)
    assert rows[second_content][:4] == (1, 0, 1, 0)
    assert activity[0][1:4] == (3, 1, 22)


@pytest.mark.parametrize("kind", ["unknown", "duplicate"])
async def test_batches_without_accepted_answers_do_not_touch_activity_or_streak(
    client, database_url, user_id, auth_headers, kind
):
    content_id = published_content_ids(database_url, 1)[0]
    headers = auth_headers(subject=user_id)
    answer_id = uuid.uuid4()
    with study_user(database_url, user_id):
        await provision(client, headers)
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                "UPDATE user_stats SET current_streak=6, longest_streak=8 WHERE user_id=%s",
                (user_id,),
            )
        if kind == "duplicate":
            original = answer(content_id, correct=True, client_answer_id=answer_id)
            first = await client.post(
                "/v1/study/answers",
                headers=headers,
                json={"answers": [original]},
            )
            assert first.status_code == 200
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute(
                    "UPDATE user_stats SET current_streak=6, longest_streak=8 WHERE user_id=%s",
                    (user_id,),
                )
            before_activity = activity_rows(database_url, user_id)
            submitted = original
        else:
            before_activity = []
            submitted = answer(9_223_372_036_854_775_000, correct=True)

        response = await client.post(
            "/v1/study/answers", headers=headers, json={"answers": [submitted]}
        )

        assert response.status_code == 200
        assert response.json()["accepted_count"] == 0
        assert response.json()["current_streak"] == 6
        assert activity_rows(database_url, user_id) == before_activity


async def test_mid_batch_database_failure_rolls_back_all_answer_side_effects(
    client, database_url, user_id, auth_headers
):
    first_content, failing_content = published_content_ids(database_url, 2)
    headers = auth_headers(subject=user_id)
    trigger = f"fail_study_batch_{uuid.uuid4().hex}"
    function = f"{trigger}_fn"
    first_answer_id, failing_answer_id = uuid.uuid4(), uuid.uuid4()
    with study_user(database_url, user_id):
        await provision(client, headers)
        try:
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute(
                    sql.SQL(
                        """
                    CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                      IF NEW.user_id = {}
                         AND NEW.content_id = {} THEN
                        RAISE EXCEPTION 'deliberate study batch failure';
                      END IF;
                      RETURN NEW;
                    END $$
                    """
                    ).format(
                        sql.Identifier(function),
                        sql.Literal(user_id),
                        sql.Literal(failing_content),
                    )
                )
                conn.execute(
                    sql.SQL(
                        "CREATE TRIGGER {} BEFORE INSERT OR UPDATE ON user_progress "
                        "FOR EACH ROW EXECUTE FUNCTION {}()"
                    ).format(sql.Identifier(trigger), sql.Identifier(function))
                )
            try:
                failed_response = await client.post(
                    "/v1/study/answers",
                    headers=headers,
                    json={
                        "answers": [
                            answer(first_content, correct=True, client_answer_id=first_answer_id),
                            answer(
                                failing_content,
                                correct=True,
                                client_answer_id=failing_answer_id,
                            ),
                        ]
                    },
                )
            except psycopg.DatabaseError as exc:
                assert "deliberate study batch failure" in str(exc)
            else:
                assert 500 <= failed_response.status_code < 600
            assert progress_rows(database_url, user_id) == {}
            assert activity_rows(database_url, user_id) == []
        finally:
            drop_progress_trigger(database_url, trigger, function)

        retry = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={
                "answers": [
                    answer(first_content, correct=True, client_answer_id=first_answer_id),
                    answer(failing_content, correct=True, client_answer_id=failing_answer_id),
                ]
            },
        )
        assert retry.status_code == 200
        assert retry.json()["accepted_count"] == 2
        assert [result["status"] for result in retry.json()["results"]] == [
            "accepted",
            "accepted",
        ]
        rows = progress_rows(database_url, user_id)
        assert rows[first_content][:3] == (1, 1, 0)
        assert rows[failing_content][:3] == (1, 1, 0)
        assert activity_rows(database_url, user_id)[0][1:4] == (2, 0, 20)
        with psycopg.connect(database_url) as conn:
            stats = conn.execute(
                """
                SELECT current_streak, longest_streak, total_items_seen,
                       total_mastered, total_xp
                FROM user_stats WHERE user_id=%s
                """,
                (user_id,),
            ).fetchone()
        assert stats == (1, 1, 2, 0, 20)


async def test_concurrent_reversed_batches_finish_without_deadlock_and_keep_all_counts(
    client, database_url, user_id, auth_headers
):
    first_content, second_content = published_content_ids(database_url, 2)
    headers = auth_headers(subject=user_id)
    trigger = f"delay_study_batch_{uuid.uuid4().hex}"
    function = f"{trigger}_fn"
    with study_user(database_url, user_id):
        try:
            with psycopg.connect(database_url, autocommit=True) as conn:
                conn.execute(
                    sql.SQL(
                        """
                    CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN
                      IF NEW.user_id = {} THEN
                        PERFORM pg_sleep(0.2);
                      END IF;
                      RETURN NEW;
                    END $$
                    """
                    ).format(sql.Identifier(function), sql.Literal(user_id))
                )
                conn.execute(
                    sql.SQL(
                        "CREATE TRIGGER {} BEFORE INSERT OR UPDATE ON user_progress "
                        "FOR EACH ROW EXECUTE FUNCTION {}()"
                    ).format(sql.Identifier(trigger), sql.Identifier(function))
                )
            responses = await asyncio.wait_for(
                asyncio.gather(
                    client.post(
                        "/v1/study/answers",
                        headers=headers,
                        json={
                            "answers": [
                                answer(first_content, correct=True),
                                answer(second_content, correct=False),
                            ]
                        },
                    ),
                    client.post(
                        "/v1/study/answers",
                        headers=headers,
                        json={
                            "answers": [
                                answer(second_content, correct=True),
                                answer(first_content, correct=False),
                            ]
                        },
                    ),
                ),
                timeout=10,
            )
        finally:
            drop_progress_trigger(database_url, trigger, function)
        assert [response.status_code for response in responses] == [200, 200]
        rows = progress_rows(database_url, user_id)
        assert rows[first_content][:3] == (2, 1, 1)
        assert rows[second_content][:3] == (2, 1, 1)
        assert activity_rows(database_url, user_id)[0][1:4] == (4, 0, 24)


async def test_activity_uses_each_users_local_day_for_the_same_utc_instant(
    client, database_url, auth_headers
):
    instant = datetime(2026, 8, 1, 2, tzinfo=UTC)
    content_id = published_content_ids(database_url, 1)[0]
    auckland_user, los_angeles_user = uuid.uuid4(), uuid.uuid4()
    expected_dates = {
        auckland_user: datetime(2026, 8, 1).date(),
        los_angeles_user: datetime(2026, 7, 31).date(),
    }
    timezones = {
        auckland_user: "Pacific/Auckland",
        los_angeles_user: "America/Los_Angeles",
    }

    with (
        fixed_utc_now(client, instant),
        study_user(database_url, auckland_user),
        study_user(database_url, los_angeles_user),
    ):
        for subject in (auckland_user, los_angeles_user):
            headers = auth_headers(subject=subject)
            await provision(client, headers)
            patched = await client.patch(
                "/v1/me/preferences",
                headers=headers,
                json={"timezone": timezones[subject]},
            )
            assert patched.status_code == 200
            response = await client.post(
                "/v1/study/answers",
                headers=headers,
                json={"answers": [answer(content_id, correct=True)]},
            )
            assert response.status_code == 200
            assert activity_rows(database_url, subject)[0][0] == expected_dates[subject]


async def test_streak_same_day_consecutive_day_and_gap_updates_once_per_batch(
    client, database_url, user_id, auth_headers
):
    instant = datetime(2026, 8, 1, 2, tzinfo=UTC)
    local_today = datetime(2026, 7, 31).date()
    content_id = published_content_ids(database_url, 1)[0]
    headers = auth_headers(subject=user_id)
    with fixed_utc_now(client, instant), study_user(database_url, user_id):
        await provision(client, headers)
        patched = await client.patch(
            "/v1/me/preferences",
            headers=headers,
            json={"timezone": "America/Los_Angeles"},
        )
        assert patched.status_code == 200
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                """
                UPDATE user_stats
                   SET current_streak = 2, longest_streak = 5, last_activity_date = %s
                 WHERE user_id = %s
                """,
                (local_today - timedelta(days=1), user_id),
            )
        consecutive = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=True), answer(content_id, correct=True)]},
        )
        same_day = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=True)]},
        )
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute(
                "UPDATE user_stats SET last_activity_date = %s WHERE user_id = %s",
                (local_today - timedelta(days=3), user_id),
            )
            conn.execute("DELETE FROM user_daily_activity WHERE user_id = %s", (user_id,))
        gap = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=False)]},
        )

        with psycopg.connect(database_url) as conn:
            stats = conn.execute(
                "SELECT current_streak, longest_streak FROM user_stats WHERE user_id = %s",
                (user_id,),
            ).fetchone()

    assert consecutive.json()["current_streak"] == 3
    assert same_day.json()["current_streak"] == 3
    assert gap.json()["current_streak"] == 1
    assert stats == (1, 5)


@pytest.mark.parametrize(
    "daily_minutes,total_ms,expected",
    [
        (5, 299_000, False),
        (5, 300_000, True),
        (15, 899_000, False),
        (15, 900_000, True),
        (30, 1_799_000, False),
        (30, 1_800_000, True),
    ],
)
async def test_daily_goal_thresholds(
    client, database_url, user_id, auth_headers, daily_minutes, total_ms, expected
):
    content_id = published_content_ids(database_url, 1)[0]
    headers = auth_headers(subject=user_id)
    with study_user(database_url, user_id):
        await provision(client, headers)
        patched = await client.patch(
            "/v1/me/preferences", headers=headers, json={"daily_minutes": daily_minutes}
        )
        assert patched.status_code == 200
        response = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={
                "answers": [
                    answer(content_id, correct=True, duration_ms=duration)
                    for duration in (
                        [300_000] * (total_ms // 300_000)
                        + ([total_ms % 300_000] if total_ms % 300_000 else [])
                    )
                ]
            },
        )
        assert response.status_code == 200
        assert activity_rows(database_url, user_id)[0][4] is expected


async def test_null_daily_goal_is_met_by_any_accepted_activity(
    client, database_url, user_id, auth_headers
):
    content_id = published_content_ids(database_url, 1)[0]
    headers = auth_headers(subject=user_id)
    with study_user(database_url, user_id):
        await provision(client, headers)
        response = await client.post(
            "/v1/study/answers",
            headers=headers,
            json={"answers": [answer(content_id, correct=False)]},
        )
        assert response.status_code == 200
        assert activity_rows(database_url, user_id)[0][4] is True


@pytest.mark.parametrize(
    ("timezone", "local_today"),
    [
        ("Pacific/Auckland", datetime(2026, 8, 1).date()),
        ("America/Los_Angeles", datetime(2026, 7, 31).date()),
    ],
)
async def test_me_stats_uses_local_today_for_totals_and_last_30_dates(
    client, database_url, user_id, auth_headers, timezone, local_today
):
    assert (await client.get("/v1/me/stats")).status_code == 401
    instant = datetime(2026, 8, 1, 2, tzinfo=UTC)
    headers = auth_headers(subject=user_id)
    with fixed_utc_now(client, instant), study_user(database_url, user_id):
        await provision(client, headers)
        patched = await client.patch(
            "/v1/me/preferences", headers=headers, json={"timezone": timezone}
        )
        assert patched.status_code == 200
        with psycopg.connect(database_url, autocommit=True) as conn:
            dates = [
                local_today - timedelta(days=30),
                local_today - timedelta(days=29),
                local_today,
            ]
            conn.execute(
                """
                UPDATE user_stats
                   SET current_streak = 2, longest_streak = 4, total_items_seen = 8,
                       total_mastered = 3, total_xp = 90, last_activity_date = %s
                 WHERE user_id = %s
                """,
                (local_today, user_id),
            )
            conn.executemany(
                """
                INSERT INTO user_daily_activity
                    (user_id, activity_date, items_reviewed, seconds_spent, xp, goal_met)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (user_id, day, index + 1, 60, 10, day == local_today)
                    for index, day in enumerate(dates)
                ],
            )
        response = await client.get(
            "/v1/me/stats", headers=headers, params={"user_id": str(uuid.uuid4())}
        )

    assert response.status_code == 200
    assert response.json() == {
        "current_streak": 2,
        "longest_streak": 4,
        "total_items_seen": 8,
        "total_mastered": 3,
        "total_xp": 90,
        "today_items_reviewed": 3,
        "today_goal_met": True,
        "activity_dates": [dates[1].isoformat(), dates[2].isoformat()],
    }
