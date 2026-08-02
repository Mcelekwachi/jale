from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.schemas import PreferencesPatch, UserPreferences, patch_values


@pytest.fixture(scope="session")
def seeded_database():
    """These schema-only tests do not require the integration database."""
    return None


@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_users():
    yield


def test_preferences_patch_exposes_language_codes_only():
    payload = PreferencesPatch(active_language="ibo", meta_language="nld")

    assert patch_values(payload) == {
        "active_language": "ibo",
        "meta_language": "nld",
    }
    assert "active_language_id" not in PreferencesPatch.model_fields
    assert "meta_language_id" not in PreferencesPatch.model_fields


def test_user_preferences_serializes_language_codes_only():
    preferences = UserPreferences(
        active_language="ibo",
        meta_language=None,
        reminder_enabled=False,
        timezone="UTC",
        placement_skipped=False,
        onboarding_status="not_started",
        updated_at=datetime.now(UTC),
    )

    body = preferences.model_dump()
    assert body["active_language"] == "ibo"
    assert body["meta_language"] is None
    assert not any(key.endswith("_language_id") for key in body)
