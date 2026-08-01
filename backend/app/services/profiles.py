from __future__ import annotations

from fastapi import HTTPException

from app.db import fetch_one

_PUBLIC_PROFILE_SQL = """
SELECT u.display_name,
       stats.current_streak,
       stats.longest_streak,
       stats.total_mastered,
       language.code AS language,
       to_char(u.created_at AT TIME ZONE 'UTC', 'YYYY-MM') AS joined_month
  FROM app_users u
  JOIN user_stats stats ON stats.user_id=u.id
  JOIN user_preferences preferences ON preferences.user_id=u.id
  JOIN languages language ON language.id=preferences.active_language_id
 WHERE u.share_slug=%(share_slug)s
   AND u.is_active
"""


async def get_public_profile(share_slug: str) -> dict:
    profile = await fetch_one(_PUBLIC_PROFILE_SQL, {"share_slug": share_slug})
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return profile
