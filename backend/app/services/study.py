"""Study sessions.

Turns a track unit (which is a *query*, not a fixed list) into the items the
client renders. Each mode gets a different shape:

    flashcard        target -> english, audio
    quiz             english prompt, four options, one correct
    phrase_practice  target -> english, plus literal gloss and toned text
    proverbs         target, meaning, literal gloss and the cultural lesson

Distractors for quiz mode are drawn from the same category first, then the
same content type, so options are plausible rather than absurd. If a category
is too small to supply three wrong answers the pool widens automatically.
"""

from __future__ import annotations

import random

from app.config import get_settings
from app.db import fetch_all, fetch_one

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
       c.target_text, c.target_text_toned, ct.translation,
       ml.code AS meta_language, ct.literal_translation, ct.cultural_note,
       c.example_sentence, c.example_translation,
       c.audio_url, c.audio_state, c.verified, c.flag_count
  FROM content_items c
  JOIN content_translations ct ON ct.content_id = c.id
  JOIN languages ml ON ml.id = ct.meta_language_id
 WHERE c.language_id = %(language_id)s
   AND ml.code = %(meta_language)s
   AND c.status = 'published'
   AND (%(category_id)s::smallint    IS NULL OR c.category_id      = %(category_id)s)
   AND (%(content_type)s::content_type IS NULL OR c.content_type   = %(content_type)s)
   AND (%(difficulty)s::difficulty_level IS NULL OR c.difficulty_level = %(difficulty)s)
 ORDER BY c.sort_order, c.id
 LIMIT %(limit)s
"""

# Distractor pool: same category first (plausible), widening to same content
# type when the category cannot supply enough wrong answers.
# Returns target-language text because that is what the options are made of —
# the prompt is English and the learner picks the Igbo.
_DISTRACTOR_SQL = """
SELECT c.target_text AS text
  FROM content_items c
 WHERE c.language_id = %(language_id)s
   AND c.status = 'published'
   AND c.id <> ALL(%(exclude_ids)s)
   AND c.content_type = %(content_type)s
 ORDER BY (c.category_id IS DISTINCT FROM %(category_id)s), random()
 LIMIT %(limit)s
"""


async def get_unit(language: str, slug: str, position: int) -> dict | None:
    return await fetch_one(_UNIT_SQL, {"language": language, "slug": slug, "position": position})


def _shape(row: dict, mode: str, options: list[dict] | None = None) -> dict:
    """Map a content row onto the StudyItem shape for a given mode."""
    base = {
        "id": row["id"],
        "content_type": row["content_type"],
        "meta_language": row["meta_language"],
        "audio_url": row["audio_url"],
        "audio_state": row["audio_state"],
        "verified": row["verified"],
        "flag_count": row["flag_count"],
        "target_text_toned": row["target_text_toned"],
        "literal_translation": None,
        "cultural_note": None,
        "example_sentence": None,
        "example_translation": None,
        "options": None,
    }

    if mode == "quiz":
        # Prompt in English, answer in the target language: recall, not recognition.
        base |= {
            "prompt": row["translation"],
            "answer": row["target_text"],
            "options": options,
        }
        return base

    base |= {"prompt": row["target_text"], "answer": row["translation"]}

    if mode == "phrase_practice":
        base |= {
            "literal_translation": row["literal_translation"],
            "example_sentence": row["example_sentence"],
            "example_translation": row["example_translation"],
        }
    elif mode == "proverbs":
        # The cultural lesson is the point of this mode, not a footnote.
        base |= {
            "literal_translation": row["literal_translation"],
            "cultural_note": row["cultural_note"],
        }

    return base


async def build_session(
    language: str, slug: str, position: int, shuffle_seed: int | None = None
) -> dict | None:
    unit = await get_unit(language, slug, position)
    if unit is None:
        return None

    rows = await fetch_all(
        _ITEMS_SQL,
        {
            "language_id": unit["language_id"],
            "meta_language": get_settings().default_meta_language,
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
        # One pooled query rather than one per item.
        ids = [r["id"] for r in rows]
        pool = await fetch_all(
            _DISTRACTOR_SQL,
            {
                "language_id": unit["language_id"],
                "exclude_ids": ids,
                "content_type": rows[0]["content_type"],
                "category_id": unit["filter_category_id"],
                "limit": max(12, len(rows) * 3),
            },
        )
        pool_texts = [p["text"] for p in pool]
        rng = random.Random(shuffle_seed)

        for row in rows:
            wrong = [t for t in pool_texts if t != row["target_text"]]
            picked = rng.sample(wrong, k=min(3, len(wrong)))
            # Correct answer is the target text; distractors must be too.
            options = [{"text": row["target_text"], "is_correct": True}]
            options += [{"text": t, "is_correct": False} for t in picked]
            rng.shuffle(options)
            items.append(_shape(row, mode, options))
    else:
        items = [_shape(row, mode) for row in rows]

    return {
        "track": unit["track_slug"],
        "unit_position": unit["position"],
        "unit_title": unit["title"],
        "mode": mode,
        "items": items,
    }
