from __future__ import annotations


def content_filter_sql(translation_expression: str) -> str:
    """Return filters shared by public and administrative content listings."""
    return f"""
       AND (%(content_type)s::content_type IS NULL OR c.content_type = %(content_type)s)
       AND (%(difficulty)s::difficulty_level IS NULL OR c.difficulty_level = %(difficulty)s)
       AND (%(category)s::text IS NULL OR cat.slug = %(category)s)
       AND (%(verified)s::boolean IS NULL OR c.verified = %(verified)s)
       AND (
             %(q)s::text IS NULL
             OR c.target_text ILIKE '%%' || %(q)s || '%%'
             OR {translation_expression} ILIKE '%%' || %(q)s || '%%'
           )
    """
