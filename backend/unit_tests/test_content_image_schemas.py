from app.admin_schemas import (
    AdminContentListItem,
    AdminContentPatch,
    AdminContentState,
)
from app.schemas import ContentItem, StudyItem


def test_content_response_models_expose_image_metadata():
    for model in (ContentItem, StudyItem, AdminContentListItem, AdminContentState):
        fields = model.model_json_schema()["properties"]
        assert "image_url" in fields
        assert "image_attribution" in fields


def test_admin_content_patch_accepts_nullable_image_metadata():
    patch = AdminContentPatch(
        image_url="https://example.test/cat.png",
        image_attribution="Artist Name, CC BY 4.0",
    )
    assert patch.model_dump(exclude_unset=True) == {
        "image_url": "https://example.test/cat.png",
        "image_attribution": "Artist Name, CC BY 4.0",
    }

    cleared = AdminContentPatch(image_url=None, image_attribution=None)
    assert cleared.model_dump(exclude_unset=True) == {
        "image_url": None,
        "image_attribution": None,
    }
