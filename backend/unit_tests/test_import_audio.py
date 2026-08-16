from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "db" / "seed"))

import import_audio  # noqa: E402

ITEMS = [
    {
        "id": 1,
        "source_key": "ibo:word:ndewo",
        "content_type": "word",
        "target_text": "Ndewo",
        "translation": "Hello",
        "audio_url": None,
        "audio_state": "missing",
    },
    {
        "id": 2,
        "source_key": "ibo:phrase:kedu-ka-i-mere",
        "content_type": "phrase",
        "target_text": "Kedu ka i mere?",
        "translation": "How are you?",
        "audio_url": None,
        "audio_state": "missing",
    },
]


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = list(connection.rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        if query.lstrip().startswith("SELECT"):
            self.rows = list(self.connection.rows)
            return
        self.connection.updates.append(params)
        if self.connection.fail_after == len(self.connection.updates):
            raise RuntimeError("database write failed")

    def fetchall(self):
        return self.rows


class FakeTransaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_args):
        if exc_type:
            self.connection.updates.clear()
            self.connection.rolled_back = True
        else:
            self.connection.committed = True
        return False


class FakeConnection:
    def __init__(self, rows, *, fail_after=None):
        self.rows = rows
        self.updates = []
        self.fail_after = fail_after
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return FakeCursor(self)

    def transaction(self):
        return FakeTransaction(self)


def options(**overrides):
    values = {
        "language": "ibo",
        "bucket": "audio",
        "folder": "Igbo",
        "extension": "mp3",
        "base_url": "https://project.supabase.co",
        "audio_state": "verified",
        "dry_run": False,
        "export_worklist": None,
    }
    values.update(overrides)
    return import_audio.ImportOptions(**values)


def test_found_recording_sets_expected_url_and_state():
    conn = FakeConnection([ITEMS[0]])

    result = import_audio.run_import(conn, options(), head_exists=lambda _url: True)

    expected = (
        "https://project.supabase.co/storage/v1/object/public/" "audio/Igbo/ibo_word_ndewo.mp3"
    )
    assert conn.updates == [(expected, "verified", 1)]
    assert result.newly_linked == 1
    assert result.missing == []


def test_missing_recording_is_untouched_and_listed():
    conn = FakeConnection([ITEMS[1]])

    result = import_audio.run_import(conn, options(), head_exists=lambda _url: False)

    assert conn.updates == []
    assert result.missing == ["ibo:phrase:kedu-ka-i-mere"]


def test_rerun_changes_nothing_when_url_and_state_match():
    expected = import_audio.public_url(options(), "ibo:word:ndewo")
    row = {**ITEMS[0], "audio_url": expected, "audio_state": "verified"}
    conn = FakeConnection([row])

    result = import_audio.run_import(conn, options(), head_exists=lambda _url: True)

    assert conn.updates == []
    assert result.already_linked == 1


def test_verified_recording_is_not_downgraded_to_placeholder():
    existing = "https://recordings.example/approved.mp3"
    row = {**ITEMS[0], "audio_url": existing, "audio_state": "verified"}
    conn = FakeConnection([row])

    result = import_audio.run_import(
        conn, options(audio_state="placeholder"), head_exists=lambda _url: True
    )

    assert conn.updates == []
    assert result.unexpected_urls == [("ibo:word:ndewo", existing)]


def test_placeholder_import_fills_verified_item_without_downgrading_state():
    row = {**ITEMS[0], "audio_url": None, "audio_state": "verified"}
    conn = FakeConnection([row])

    import_audio.run_import(conn, options(audio_state="placeholder"), head_exists=lambda _url: True)

    expected = import_audio.public_url(options(), "ibo:word:ndewo")
    assert conn.updates == [(expected, "verified", 1)]


def test_unexpected_existing_url_is_reported_when_expected_recording_is_missing():
    existing = "https://recordings.example/other.mp3"
    row = {**ITEMS[0], "audio_url": existing, "audio_state": "placeholder"}
    conn = FakeConnection([row])

    result = import_audio.run_import(conn, options(), head_exists=lambda _url: False)

    assert conn.updates == []
    assert result.missing == ["ibo:word:ndewo"]
    assert result.unexpected_urls == [("ibo:word:ndewo", existing)]


def test_dry_run_reports_change_without_writing():
    conn = FakeConnection([ITEMS[0]])

    result = import_audio.run_import(conn, options(dry_run=True), head_exists=lambda _url: True)

    assert conn.updates == []
    assert result.newly_linked == 1
    assert result.changes == ["ibo:word:ndewo"]


def test_public_url_uses_capitalized_folder_and_filename_convention():
    assert import_audio.public_url(options(), "ibo:proverb:igwe-bu-ike") == (
        "https://project.supabase.co/storage/v1/object/public/"
        "audio/Igbo/ibo_proverb_igwe-bu-ike.mp3"
    )


def test_worklist_contains_exact_filename_column(tmp_path):
    path = tmp_path / "recordings.csv"
    conn = FakeConnection([ITEMS[1]])

    import_audio.run_import(
        conn,
        options(export_worklist=path),
        head_exists=lambda _url: False,
    )

    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "source_key": "ibo:phrase:kedu-ka-i-mere",
            "content_type": "phrase",
            "target_text": "Kedu ka i mere?",
            "translation": "How are you?",
            "filename": "ibo_phrase_kedu-ka-i-mere.mp3",
        }
    ]


def test_write_failure_rolls_back_every_update():
    conn = FakeConnection(ITEMS, fail_after=2)

    with pytest.raises(RuntimeError, match="database write failed"):
        import_audio.run_import(conn, options(), head_exists=lambda _url: True)

    assert conn.updates == []
    assert conn.rolled_back is True
    assert conn.committed is False
