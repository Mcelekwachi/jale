from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from app.db import get_pool
from app.schemas import StudyAnswer

_INTERVALS = {
    0: timedelta(minutes=10),
    1: timedelta(days=1),
    2: timedelta(days=3),
    3: timedelta(days=7),
    4: timedelta(days=21),
    5: timedelta(days=60),
}
_BIGINT_MIN = -(2**63)
_BIGINT_MAX = 2**63 - 1


def get_utc_now() -> datetime:
    return datetime.now(UTC)


def _local_date(now: datetime, timezone: str):
    return now.astimezone(ZoneInfo(timezone)).date()


async def _context(
    conn, user_id: UUID, *, lock: Literal["share", "update"] | None = None
) -> dict[str, Any]:
    lock_clause = {
        None: "",
        "share": " FOR SHARE OF s",
        "update": " FOR UPDATE OF s",
    }[lock]
    cursor = await conn.execute(
        """
        SELECT s.*, p.timezone, p.daily_minutes
          FROM user_stats s JOIN user_preferences p ON p.user_id = s.user_id
         WHERE s.user_id = %(user_id)s
        """
        + lock_clause,
        {"user_id": user_id},
    )
    row = await cursor.fetchone()
    if row is None:
        raise RuntimeError("authenticated user study state is missing")
    return dict(row)


async def get_stats(user_id: UUID, now: datetime) -> dict[str, Any]:
    async with get_pool().connection() as conn:
        context = await _context(conn, user_id, lock="share")
        today = _local_date(now, context["timezone"])
        cursor = await conn.execute(
            """
            SELECT activity_date, items_reviewed, goal_met
              FROM user_daily_activity
             WHERE user_id = %(user_id)s
               AND activity_date BETWEEN %(start)s AND %(today)s
             ORDER BY activity_date
            """,
            {"user_id": user_id, "start": today - timedelta(days=29), "today": today},
        )
        activity = [dict(row) for row in await cursor.fetchall()]
    today_row = next((row for row in activity if row["activity_date"] == today), None)
    return {
        "current_streak": context["current_streak"],
        "longest_streak": context["longest_streak"],
        "total_items_seen": context["total_items_seen"],
        "total_mastered": context["total_mastered"],
        "total_xp": context["total_xp"],
        "today_items_reviewed": today_row["items_reviewed"] if today_row else 0,
        "today_goal_met": today_row["goal_met"] if today_row else False,
        "activity_dates": [row["activity_date"] for row in activity],
    }


async def record_answers(user_id: UUID, answers: list[StudyAnswer], now: datetime) -> dict:
    async with get_pool().connection() as conn, conn.transaction():
        context = await _context(conn, user_id, lock="update" if answers else "share")
        today = _local_date(now, context["timezone"])
        if not answers:
            cursor = await conn.execute(
                "SELECT xp FROM user_daily_activity WHERE user_id=%(user_id)s AND activity_date=%(today)s",
                {"user_id": user_id, "today": today},
            )
            activity = await cursor.fetchone()
            return {
                "results": [],
                "accepted_count": 0,
                "skipped_count": 0,
                "current_streak": context["current_streak"],
                "today_xp": activity["xp"] if activity else 0,
            }

        content_ids = sorted(
            {item.content_id for item in answers if _BIGINT_MIN <= item.content_id <= _BIGINT_MAX}
        )
        published: set[int] = set()
        if content_ids:
            cursor = await conn.execute(
                "SELECT id FROM content_items WHERE id = ANY(%(ids)s) AND status='published'",
                {"ids": content_ids},
            )
            published = {row["id"] for row in await cursor.fetchall()}
        client_ids = [
            item.client_answer_id for item in answers if item.client_answer_id is not None
        ]
        existing: dict[str, int] = {}
        if client_ids:
            cursor = await conn.execute(
                "SELECT client_answer_id, content_id FROM study_answer_receipts "
                "WHERE user_id=%(user_id)s AND client_answer_id = ANY(%(ids)s)",
                {"user_id": user_id, "ids": client_ids},
            )
            existing = {
                row["client_answer_id"]: row["content_id"] for row in await cursor.fetchall()
            }

        statuses: list[str] = []
        accepted_indexes: list[int] = []
        claimed = dict(existing)
        for index, item in enumerate(answers):
            if item.content_id not in published:
                statuses.append("unknown_content")
            elif item.client_answer_id is not None and item.client_answer_id in claimed:
                statuses.append(
                    "duplicate"
                    if claimed[item.client_answer_id] == item.content_id
                    else "id_conflict"
                )
            else:
                if item.client_answer_id is not None:
                    cursor = await conn.execute(
                        """INSERT INTO study_answer_receipts(user_id, client_answer_id, content_id)
                           VALUES (%(user_id)s, %(answer_id)s, %(content_id)s)
                           ON CONFLICT DO NOTHING RETURNING content_id""",
                        {
                            "user_id": user_id,
                            "answer_id": item.client_answer_id,
                            "content_id": item.content_id,
                        },
                    )
                    inserted = await cursor.fetchone()
                    if inserted is None:
                        cursor = await conn.execute(
                            "SELECT content_id FROM study_answer_receipts "
                            "WHERE user_id=%(user_id)s AND client_answer_id=%(answer_id)s",
                            {"user_id": user_id, "answer_id": item.client_answer_id},
                        )
                        stored = await cursor.fetchone()
                        claimed[item.client_answer_id] = stored["content_id"]
                        statuses.append(
                            "duplicate"
                            if stored["content_id"] == item.content_id
                            else "id_conflict"
                        )
                        continue
                    claimed[item.client_answer_id] = item.content_id
                statuses.append("accepted")
                accepted_indexes.append(index)

        accepted_content_ids = sorted({answers[index].content_id for index in accepted_indexes})
        for content_id in accepted_content_ids:
            await conn.execute(
                """INSERT INTO user_progress(user_id, content_id, first_seen_at)
                     VALUES (%(user_id)s, %(content_id)s, %(now)s)
                     ON CONFLICT DO NOTHING""",
                {"user_id": user_id, "content_id": content_id, "now": now},
            )
        boxes: dict[int, int] = {}
        if accepted_content_ids:
            cursor = await conn.execute(
                """SELECT content_id, leitner_box FROM user_progress
                     WHERE user_id=%(user_id)s AND content_id=ANY(%(ids)s)
                     ORDER BY content_id FOR UPDATE""",
                {"user_id": user_id, "ids": accepted_content_ids},
            )
            boxes = {row["content_id"]: row["leitner_box"] for row in await cursor.fetchall()}

        states: dict[int, dict[str, Any]] = {}
        for index in sorted(accepted_indexes, key=lambda value: (answers[value].content_id, value)):
            item = answers[index]
            box = min(boxes[item.content_id] + 1, 5) if item.correct else 0
            boxes[item.content_id] = box
            due = now + _INTERVALS[box]
            cursor = await conn.execute(
                """UPDATE user_progress SET
                       times_seen=times_seen+1,
                       times_correct=times_correct+%(correct)s,
                       times_incorrect=times_incorrect+%(incorrect)s,
                       leitner_box=%(box)s, due_at=%(due)s,
                       mastered=%(mastered)s, last_reviewed_at=%(now)s
                     WHERE user_id=%(user_id)s AND content_id=%(content_id)s
                     RETURNING leitner_box, due_at, mastered""",
                {
                    "user_id": user_id,
                    "content_id": item.content_id,
                    "correct": int(item.correct),
                    "incorrect": int(not item.correct),
                    "box": box,
                    "due": due,
                    "mastered": box == 5,
                    "now": now,
                },
            )
            states[index] = dict(await cursor.fetchone())

        accepted = len(accepted_indexes)
        if accepted:
            milliseconds = sum(
                max(0, min(item.duration_ms or 0, 300_000))
                for i, item in enumerate(answers)
                if i in states
            )
            seconds = milliseconds // 1000
            xp = sum(10 if answers[i].correct else 2 for i in accepted_indexes)
            threshold = context["daily_minutes"]
            await conn.execute(
                """INSERT INTO user_daily_activity(user_id, activity_date, items_reviewed, seconds_spent, xp, goal_met)
                     VALUES (%(user_id)s, %(today)s, %(items)s, %(seconds)s, %(xp)s,
                             CASE WHEN %(threshold)s IS NULL THEN true ELSE %(items)s >= %(threshold)s END)
                     ON CONFLICT (user_id, activity_date) DO UPDATE SET
                       items_reviewed=user_daily_activity.items_reviewed+EXCLUDED.items_reviewed,
                       seconds_spent=user_daily_activity.seconds_spent+EXCLUDED.seconds_spent,
                       xp=user_daily_activity.xp+EXCLUDED.xp,
                       goal_met=CASE WHEN %(threshold)s IS NULL THEN true
                         ELSE user_daily_activity.items_reviewed+EXCLUDED.items_reviewed >= %(threshold)s END""",
                {
                    "user_id": user_id,
                    "today": today,
                    "items": accepted,
                    "seconds": seconds,
                    "xp": xp,
                    "threshold": threshold,
                },
            )
            last = context["last_activity_date"]
            streak = (
                context["current_streak"]
                if last == today
                else (context["current_streak"] + 1 if last == today - timedelta(days=1) else 1)
            )
            await conn.execute(
                """UPDATE user_stats SET current_streak=%(streak)s,
                       longest_streak=GREATEST(longest_streak, %(streak)s),
                       last_activity_date=%(today)s,
                       total_items_seen=(SELECT count(*) FROM user_progress WHERE user_id=%(user_id)s),
                       total_mastered=(SELECT count(*) FROM user_progress WHERE user_id=%(user_id)s AND mastered),
                       total_xp=(SELECT coalesce(sum(xp),0) FROM user_daily_activity WHERE user_id=%(user_id)s),
                       updated_at=%(now)s WHERE user_id=%(user_id)s""",
                {"user_id": user_id, "streak": streak, "today": today, "now": now},
            )
            context["current_streak"] = streak

        progress_ids = sorted(
            {item.content_id for i, item in enumerate(answers) if statuses[i] == "duplicate"}
        )
        duplicate_states = {}
        if progress_ids:
            cursor = await conn.execute(
                "SELECT content_id, leitner_box, due_at, mastered FROM user_progress "
                "WHERE user_id=%(user_id)s AND content_id=ANY(%(ids)s)",
                {"user_id": user_id, "ids": progress_ids},
            )
            duplicate_states = {row["content_id"]: dict(row) for row in await cursor.fetchall()}
        results = []
        for i, item in enumerate(answers):
            state = (
                states.get(i)
                if statuses[i] == "accepted"
                else duplicate_states.get(item.content_id)
            )
            results.append(
                {
                    "content_id": item.content_id,
                    "client_answer_id": item.client_answer_id,
                    "status": statuses[i],
                    "leitner_box": state["leitner_box"] if state else None,
                    "due_at": state["due_at"] if state else None,
                    "mastered": state["mastered"] if state else False,
                }
            )
        cursor = await conn.execute(
            "SELECT xp FROM user_daily_activity WHERE user_id=%(user_id)s AND activity_date=%(today)s",
            {"user_id": user_id, "today": today},
        )
        activity = await cursor.fetchone()
        return {
            "results": results,
            "accepted_count": accepted,
            "skipped_count": len(answers) - accepted,
            "current_streak": context["current_streak"],
            "today_xp": activity["xp"] if activity else 0,
        }
