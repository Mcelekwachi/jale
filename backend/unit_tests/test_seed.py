from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "db" / "seed"))

import seed  # noqa: E402


class ContentCursor:
    def __init__(self):
        self.calls = []
        self.results = [None, {"was_insert": True}]

    def execute(self, query, params):
        self.calls.append((query, params))

    def fetchone(self):
        return self.results.pop(0)


def test_upsert_content_populates_example_translation_without_blanking_existing_value():
    cursor = ContentCursor()
    rows = [
        {
            "source_key": "ibo:word:alphabet-a",
            "content_type": "word",
            "category_slug": "alphabet",
            "difficulty": "beginner",
            "target_text": "a",
            "target_text_toned": "",
            "example_sentence": "Aka",
            "example_translation": "hand",
        }
    ]

    seed.upsert_content(cursor, 1, None, {"alphabet": 2}, rows)

    insert_query, insert_params = cursor.calls[1]
    assert "example_translation" in insert_query
    assert "ELSE COALESCE(EXCLUDED.example_translation," in " ".join(insert_query.split())
    assert insert_params["example_translation"] == "hand"


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
        "source_key,translation,literal_translation,cultural_note\nibo:word:missing,Ontbrekend,,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed, "CONTENT_ROOT", tmp_path)

    plan, errors = seed.prepare_language("ibo", {"nl": "nld"})

    assert plan is None
    assert any("nl.csv:2: unknown source_key 'ibo:word:missing'" in error for error in errors)


def test_number_seed_contains_nine_and_compounds_through_twenty():
    errors = []
    _, file_codes = seed.load_language_registry(errors)
    plan, language_errors = seed.prepare_language("ibo", file_codes)

    assert errors == []
    assert language_errors == []
    assert plan is not None

    expected = {
        "ibo:word:itolu": ("Itolu", "beginner", "Nine", "9"),
        "ibo:word:number-11": ("Iri na otu", "intermediate", "Eleven", "11"),
        "ibo:word:number-12": ("Iri na abụọ", "intermediate", "Twelve", "12"),
        "ibo:word:number-13": ("Iri na atọ", "intermediate", "Thirteen", "13"),
        "ibo:word:number-14": ("Iri na anọ", "intermediate", "Fourteen", "14"),
        "ibo:word:number-15": ("Iri na ise", "intermediate", "Fifteen", "15"),
        "ibo:word:number-16": ("Iri na isii", "intermediate", "Sixteen", "16"),
        "ibo:word:number-17": ("Iri na asaa", "intermediate", "Seventeen", "17"),
        "ibo:word:number-18": ("Iri na asatọ", "intermediate", "Eighteen", "18"),
        "ibo:word:number-19": ("Iri na itolu", "intermediate", "Nineteen", "19"),
        "ibo:word:number-20": ("Iri abụọ", "intermediate", "Twenty", "20"),
    }
    words = {
        row["source_key"]: row for row in plan["all_rows"]["word"] if row["source_key"] in expected
    }
    translations = {
        row["source_key"]: row
        for row in plan["translations"]
        if row["source_key"] in expected and row["meta_code"] == "eng"
    }
    compound_keys = {
        row["source_key"]
        for row in plan["all_rows"]["word"]
        if row["source_key"].startswith("ibo:word:number-")
    }

    assert set(words) == set(expected)
    assert set(translations) == set(expected)
    assert compound_keys == set(expected) - {"ibo:word:itolu"}
    for source_key, (target, difficulty, english, literal) in expected.items():
        assert words[source_key]["target_text"] == target
        assert words[source_key]["category_slug"] == "numbers"
        assert words[source_key]["difficulty"] == difficulty
        assert translations[source_key]["translation"] == english
        assert translations[source_key]["literal_translation"] == literal
