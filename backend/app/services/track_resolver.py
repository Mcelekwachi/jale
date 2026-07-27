"""Track resolution.

The entire personalisation engine is one query against track_rules. Rules are
walked in ascending priority and the first match wins; a NULL match column is
a wildcard. Adding a persona is a row in tracks.yaml, never a branch here.

Any preference may be None, because onboarding is skippable at every screen.
A user who skips everything falls through to the wildcard rule on the default
track, so there is no such thing as an unresolvable user.
"""

from __future__ import annotations

from app.db import fetch_all, fetch_one

_RESOLVE_SQL = """
SELECT t.slug, r.priority
  FROM track_rules r
  JOIN tracks t ON t.id = r.track_id
  JOIN languages l ON l.id = t.language_id
 WHERE l.code = %(language)s
   AND (r.match_age        IS NULL OR %(age)s::age_band         = ANY(r.match_age))
   AND (r.match_connection IS NULL OR %(connection)s::connection_type = ANY(r.match_connection))
   AND (r.match_goal       IS NULL OR %(goal)s::learning_goal   = ANY(r.match_goal))
   AND (r.match_style      IS NULL OR %(style)s::learning_style = ANY(r.match_style))
 ORDER BY r.priority
 LIMIT 1
"""

_TRACK_SQL = """
SELECT t.slug, t.name, t.description, t.min_difficulty, t.max_difficulty,
       t.is_default
  FROM tracks t
  JOIN languages l ON l.id = t.language_id
 WHERE l.code = %(language)s AND t.slug = %(slug)s
"""

_TRACKS_SQL = """
SELECT t.slug, t.name, t.description, t.min_difficulty, t.max_difficulty,
       t.is_default
  FROM tracks t
  JOIN languages l ON l.id = t.language_id
 WHERE l.code = %(language)s
 ORDER BY t.is_default, t.slug
"""

# `available` is computed per unit so the client can tell the difference
# between "unit not started" and "unit has no content yet".
_UNITS_SQL = """
SELECT u.position, u.title, u.mode,
       cat.slug AS category,
       u.filter_content_type AS content_type,
       u.filter_difficulty   AS difficulty,
       u.item_count,
       (SELECT count(*) FROM content_items c
         WHERE c.language_id = t.language_id
           AND c.status = 'published'
           AND (u.filter_category_id  IS NULL OR c.category_id      = u.filter_category_id)
           AND (u.filter_content_type IS NULL OR c.content_type     = u.filter_content_type)
           AND (u.filter_difficulty   IS NULL OR c.difficulty_level = u.filter_difficulty)
       ) AS available
  FROM track_units u
  JOIN tracks t ON t.id = u.track_id
  JOIN languages l ON l.id = t.language_id
  LEFT JOIN categories cat ON cat.id = u.filter_category_id
 WHERE l.code = %(language)s AND t.slug = %(slug)s
 ORDER BY u.position
"""


async def list_tracks(language: str) -> list[dict]:
    return await fetch_all(_TRACKS_SQL, {"language": language})


async def get_track(language: str, slug: str) -> dict | None:
    return await fetch_one(_TRACK_SQL, {"language": language, "slug": slug})


async def get_units(language: str, slug: str) -> list[dict]:
    return await fetch_all(_UNITS_SQL, {"language": language, "slug": slug})


async def resolve(
    language: str,
    age: str | None = None,
    connection: str | None = None,
    goal: str | None = None,
    style: str | None = None,
) -> tuple[dict | None, int | None]:
    """Return (track_row, matched_priority) for a set of onboarding answers."""
    row = await fetch_one(
        _RESOLVE_SQL,
        {
            "language": language,
            "age": age,
            "connection": connection,
            "goal": goal,
            "style": style,
        },
    )
    if row is None:
        return None, None
    track = await get_track(language, row["slug"])
    return track, row["priority"]
