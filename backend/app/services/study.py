"""Build direction-aware study sessions with per-item meta-language fallback."""

from __future__ import annotations

import random

from app.db import fetch_all, fetch_one
from app.schemas import StudyDirection

_UNIT_SQL = """
SELECT u.position, u.title, u.mode, u.item_count,
       u.filter_category_id, u.filter_content_type, u.filter_difficulty,
       t.language_id, t.slug AS track_slug
  FROM track_units u
  JOIN tracks t ON t.id = u.track_id
  JOIN languages l ON l.id = t.language_id
 WHERE l.code = %(language)s AND t.slug = %(slug)s AND u.position = %(position)s
"""

_ITEMS_SQL = """
SELECT c.id, c.content_type, c.difficulty_level, c.category_id,
       c.target_text, c.target_text_toned,
       COALESCE(requested_ct.translation, default_ct.translation) AS translation,
       %(meta_language)s AS meta_language,
       CASE WHEN requested_ct.content_id IS NULL
            THEN %(default_meta_language)s ELSE %(meta_language)s END AS meta_language_used,
       COALESCE(requested_ct.literal_translation,
                default_ct.literal_translation) AS literal_translation,
       COALESCE(requested_ct.cultural_note,
                default_ct.cultural_note) AS cultural_note,
       c.example_sentence, c.example_translation,
       c.audio_url, c.audio_state, c.verified, c.flag_count
  FROM content_items c
  JOIN languages default_ml ON default_ml.code = %(default_meta_language)s
                           AND default_ml.is_meta
  JOIN content_translations default_ct ON default_ct.content_id = c.id
                                      AND default_ct.meta_language_id = default_ml.id
  JOIN languages requested_ml ON requested_ml.code = %(meta_language)s
                             AND requested_ml.is_meta
  LEFT JOIN content_translations requested_ct ON requested_ct.content_id = c.id
                                             AND requested_ct.meta_language_id = requested_ml.id
 WHERE c.language_id = %(language_id)s
   AND c.status = 'published'
   AND (%(category_id)s::smallint IS NULL OR c.category_id = %(category_id)s)
   AND (%(content_type)s::content_type IS NULL OR c.content_type = %(content_type)s)
   AND (%(difficulty)s::difficulty_level IS NULL OR c.difficulty_level = %(difficulty)s)
 ORDER BY c.sort_order, c.id
 LIMIT %(limit)s
"""

# A single pool query supplies answer candidates for either study direction.
_DISTRACTOR_SQL = """
SELECT c.content_type, c.category_id, c.target_text,
       requested_ct.translation AS requested_translation,
       default_ct.translation AS default_translation
  FROM content_items c
  JOIN languages default_ml ON default_ml.code = %(default_meta_language)s
                           AND default_ml.is_meta
  JOIN content_translations default_ct ON default_ct.content_id = c.id
                                      AND default_ct.meta_language_id = default_ml.id
  JOIN languages requested_ml ON requested_ml.code = %(meta_language)s
                             AND requested_ml.is_meta
  LEFT JOIN content_translations requested_ct ON requested_ct.content_id = c.id
                                             AND requested_ct.meta_language_id = requested_ml.id
 WHERE c.language_id = %(language_id)s
   AND c.status = 'published'
   AND c.id <> ALL(%(exclude_ids)s)
 ORDER BY c.sort_order, c.id
"""


async def get_unit(language: str, slug: str, position: int) -> dict | None:
    return await fetch_one(_UNIT_SQL, {"language": language, "slug": slug, "position": position})


def _shape(
    row: dict,
    mode: str,
    direction: StudyDirection,
    options: list[dict] | None = None,
) -> dict:
    """Map a content row onto the StudyItem shape for a direction and mode."""
    base = {
        "id": row["id"],
        "content_type": row["content_type"],
        "meta_language": row["meta_language"],
        "meta_language_used": row["meta_language_used"],
        "audio_url": row["audio_url"],
        "audio_state": row["audio_state"],
        "verified": row["verified"],
        "flag_count": row["flag_count"],
        "target_text_toned": row["target_text_toned"],
        "literal_translation": None,
        "cultural_note": None,
        "example_sentence": None,
        "example_translation": None,
        "options": options,
    }
    if direction == StudyDirection.target_to_meta:
        base |= {"prompt": row["target_text"], "answer": row["translation"]}
    else:
        base |= {"prompt": row["translation"], "answer": row["target_text"]}

    if mode == "phrase_practice":
        base |= {
            "literal_translation": row["literal_translation"],
            "example_sentence": row["example_sentence"],
            "example_translation": row["example_translation"],
        }
    elif mode == "proverbs":
        base |= {
            "literal_translation": row["literal_translation"],
            "cultural_note": row["cultural_note"],
        }
    return base


def _pick_wrong_answers(
    pool: list[dict],
    row: dict,
    field: str,
    answer: str,
    rng: random.Random,
) -> list[str]:
    """Prefer the question's category, then widen within its content type."""
    seen = {answer}
    same_category: list[str] = []
    other_categories: list[str] = []
    for candidate in pool:
        value = candidate[field]
        if candidate["content_type"] != row["content_type"] or not value or value in seen:
            continue
        seen.add(value)
        destination = (
            same_category if candidate["category_id"] == row["category_id"] else other_categories
        )
        destination.append(value)

    picked = rng.sample(same_category, k=min(3, len(same_category)))
    remaining = 3 - len(picked)
    if remaining:
        picked += rng.sample(other_categories, k=min(remaining, len(other_categories)))
    return picked


async def build_session(
    language: str,
    slug: str,
    position: int,
    meta_language: str,
    default_meta_language: str,
    direction: StudyDirection,
    shuffle_seed: int | None = None,
) -> dict | None:
    unit = await get_unit(language, slug, position)
    if unit is None:
        return None

    rows = await fetch_all(
        _ITEMS_SQL,
        {
            "language_id": unit["language_id"],
            "meta_language": meta_language,
            "default_meta_language": default_meta_language,
            "category_id": unit["filter_category_id"],
            "content_type": unit["filter_content_type"],
            "difficulty": unit["filter_difficulty"],
            "limit": unit["item_count"],
        },
    )
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(rows)

    mode = unit["mode"]
    items: list[dict] = []
    if mode == "quiz" and rows:
        ids = [row["id"] for row in rows]
        pool = await fetch_all(
            _DISTRACTOR_SQL,
            {
                "language_id": unit["language_id"],
                "meta_language": meta_language,
                "default_meta_language": default_meta_language,
                "exclude_ids": ids,
            },
        )
        rng = random.Random(shuffle_seed)
        for row in rows:
            if direction == StudyDirection.meta_to_target:
                field = "target_text"
                answer = row["target_text"]
            elif row["meta_language_used"] == meta_language:
                field = "requested_translation"
                answer = row["translation"]
            else:
                field = "default_translation"
                answer = row["translation"]
            picked = _pick_wrong_answers(pool, row, field, answer, rng)
            options = [{"text": answer, "is_correct": True}]
            options += [{"text": text, "is_correct": False} for text in picked]
            rng.shuffle(options)
            items.append(_shape(row, mode, direction, options))
    else:
        items = [_shape(row, mode, direction) for row in rows]

    return {
        "track": unit["track_slug"],
        "unit_position": unit["position"],
        "unit_title": unit["title"],
        "mode": mode,
        "items": items,
    }
