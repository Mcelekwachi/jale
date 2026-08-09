from __future__ import annotations

import pytest
from app.schemas import PreferencesPatch, SkipOnboarding
from pydantic import ValidationError


@pytest.mark.parametrize("schema", [PreferencesPatch, SkipOnboarding])
def test_onboarding_screen_ten_is_within_api_sanity_bound(schema):
    payload = schema(onboarding_last_screen=10)

    assert payload.onboarding_last_screen == 10


@pytest.mark.parametrize("schema", [PreferencesPatch, SkipOnboarding])
@pytest.mark.parametrize("screen", [0, 21])
def test_onboarding_screen_outside_api_sanity_bound_is_rejected(schema, screen):
    with pytest.raises(ValidationError):
        schema(onboarding_last_screen=screen)
