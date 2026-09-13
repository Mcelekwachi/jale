from __future__ import annotations

import uuid

import pytest
from app.services import track_resolver


@pytest.mark.asyncio
async def test_progress_for_eight_units_uses_one_query(monkeypatch):
    calls: list[tuple[str, dict]] = []
    rows = [
        {
            "position": position,
            "title": f"Unit {position}",
            "mode": "flashcard",
            "category": None,
            "content_type": "word",
            "difficulty": "beginner",
            "item_count": 10,
            "available": 10,
            "done": 0,
            "total": 10,
            "completed": False,
        }
        for position in range(1, 9)
    ]

    async def fetch_all(sql: str, params: dict):
        calls.append((sql, params))
        return rows

    monkeypatch.setattr(track_resolver, "fetch_all", fetch_all)
    user_id = uuid.uuid4()

    result = await track_resolver.get_units_with_progress("ibo", "ibo_foundations", user_id)

    assert len(result) == 8
    assert all(unit["progress"] == {"done": 0, "total": 10} for unit in result)
    assert all("done" not in unit and "total" not in unit for unit in result)
    assert len(calls) == 1
    assert calls[0][1] == {
        "language": "ibo",
        "slug": "ibo_foundations",
        "user_id": user_id,
    }
