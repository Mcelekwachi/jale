from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "db" / "seed"))

import seed  # noqa: E402


def test_unknown_translation_source_key_fails_preflight(tmp_path, monkeypatch):
    language_dir = tmp_path / "ibo"
    translations = language_dir / "translations"
    translations.mkdir(parents=True)
    (language_dir / "language.yaml").write_text(
        "language:\n  code: ibo\n  name: Igbo\ncategories: []\n",
        encoding="utf-8",
    )
    (language_dir / "words.csv").write_text(
        "source_key,content_type,category_slug,difficulty,target_text,target_text_toned\n"
        "ibo:word:known,word,,beginner,Known,\n",
        encoding="utf-8",
    )
    (language_dir / "tracks.yaml").write_text("tracks: []\n", encoding="utf-8")
    (translations / "nl.csv").write_text(
        "source_key,translation,literal_translation,cultural_note\n"
        "ibo:word:missing,Ontbrekend,,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed, "CONTENT_ROOT", tmp_path)

    plan, errors = seed.prepare_language("ibo", {"nl": "nld"})

    assert plan is None
    assert any("nl.csv:2: unknown source_key 'ibo:word:missing'" in error for error in errors)
