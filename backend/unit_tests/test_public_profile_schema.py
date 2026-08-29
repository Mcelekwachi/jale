from __future__ import annotations

from app.schemas import PublicProfile


def test_public_profile_serializes_language_identity_from_joined_language():
    profile = PublicProfile(
        display_name="Public Learner",
        current_streak=7,
        longest_streak=19,
        total_mastered=42,
        language="ibo",
        language_name="Igbo",
        language_endonym="Asụsụ Igbo",
        joined_month="2024-03",
    )

    assert profile.model_dump() == {
        "display_name": "Public Learner",
        "current_streak": 7,
        "longest_streak": 19,
        "total_mastered": 42,
        "language": "ibo",
        "language_name": "Igbo",
        "language_endonym": "Asụsụ Igbo",
        "joined_month": "2024-03",
    }
