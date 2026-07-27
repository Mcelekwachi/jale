#!/usr/bin/env python3
"""
Jalɛ — content seed loader.

Reads content/<lang>/ and upserts into PostgreSQL. Idempotent: safe to run on
every deploy. Keys on content_items.source_key, so re-running updates text and
never touches user_progress, streaks or flags.

    python db/seed/seed.py --language ibo
    python db/seed/seed.py --language ibo --dry-run
    python db/seed/seed.py --all

Adding Yoruba later:
    mkdir content/yor && cp content/ibo/*.{yaml,csv} content/yor/ && edit
    python db/seed/seed.py --language yor
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg
import yaml
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_ROOT = REPO_ROOT / "content"

CONTENT_FILES = {
    "word": "words.csv",
    "phrase": "phrases.csv",
    "proverb": "proverbs.csv",
}

VALID_DIFFICULTY = {"beginner", "intermediate", "advanced", "native"}
VALID_MODE = {"flashcard", "quiz", "phrase_practice", "proverbs"}


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


class SeedError(Exception):
    pass


def validate_rows(rows, content_type, categories, tone_policy, path):
    """Fail loudly on structural problems. Warn on editorial ones."""
    errors, warnings = [], []
    seen_keys, seen_text = set(), set()
    toned_types = set(tone_policy.get("toned_content_types", []))

    for i, r in enumerate(rows, start=2):  # +2 = header offset, 1-indexed
        loc = f"{path.name}:{i}"

        if not r.get("source_key"):
            errors.append(f"{loc} missing source_key")
        elif r["source_key"] in seen_keys:
            errors.append(f"{loc} duplicate source_key {r['source_key']}")
        else:
            seen_keys.add(r["source_key"])

        if r.get("content_type") != content_type:
            errors.append(
                f"{loc} content_type is {r.get('content_type')!r}, expected {content_type!r}"
            )

        if not r.get("target_text"):
            errors.append(f"{loc} missing target_text")
        else:
            key = r["target_text"].strip().lower()
            if key in seen_text:
                errors.append(f"{loc} duplicate target_text {r['target_text']!r}")
            seen_text.add(key)

        if not r.get("english_translation"):
            errors.append(f"{loc} missing english_translation")

        if r.get("category_slug") not in categories:
            errors.append(f"{loc} unknown category {r.get('category_slug')!r}")

        if r.get("difficulty") not in VALID_DIFFICULTY:
            errors.append(f"{loc} bad difficulty {r.get('difficulty')!r}")

        # schema-level CHECK, caught early with a readable message
        if content_type == "proverb" and not r.get("cultural_note"):
            errors.append(f"{loc} proverb missing cultural_note")

        # tone policy: warning, never an error — policy may change per language
        toned = (r.get("target_text_toned") or "").strip()
        if toned and content_type not in toned_types:
            warnings.append(
                f"{loc} has tone marking but {content_type} is outside this language's tone policy"
            )

    return errors, warnings


# --------------------------------------------------------------------------
# upserts
# --------------------------------------------------------------------------


def upsert_language(cur, lang):
    cur.execute(
        """
        INSERT INTO languages (code, name, endonym, flag_emoji, is_active, sort_order)
        VALUES (%(code)s, %(name)s, %(endonym)s, %(flag_emoji)s,
                %(is_active)s, %(sort_order)s)
        ON CONFLICT (code) DO UPDATE SET
            name       = EXCLUDED.name,
            endonym    = EXCLUDED.endonym,
            flag_emoji = EXCLUDED.flag_emoji,
            is_active  = EXCLUDED.is_active,
            sort_order = EXCLUDED.sort_order
        RETURNING id
        """,
        {
            "code": lang["code"],
            "name": lang["name"],
            "endonym": lang.get("endonym"),
            "flag_emoji": lang.get("flag_emoji"),
            "is_active": lang.get("is_active", False),
            "sort_order": lang.get("sort_order", 100),
        },
    )
    return cur.fetchone()["id"]


def upsert_dialects(cur, language_id, dialects):
    out = {}
    for d in dialects:
        cur.execute(
            """
            INSERT INTO dialects (language_id, code, name, is_default)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (language_id, code) DO UPDATE SET
                name = EXCLUDED.name, is_default = EXCLUDED.is_default
            RETURNING id
            """,
            (language_id, d["code"], d["name"], d.get("is_default", False)),
        )
        out[d["code"]] = cur.fetchone()["id"]
    return out


def upsert_categories(cur, language_id, categories):
    out = {}
    for c in categories:
        cur.execute(
            """
            INSERT INTO categories (language_id, slug, name, icon, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (language_id, slug) DO UPDATE SET
                name = EXCLUDED.name, icon = EXCLUDED.icon,
                sort_order = EXCLUDED.sort_order
            RETURNING id
            """,
            (language_id, c["slug"], c["name"], c.get("icon"), c.get("sort_order", 100)),
        )
        out[c["slug"]] = cur.fetchone()["id"]
    return out


def nullify(value):
    """Empty CSV cells become NULL, not empty strings."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def upsert_content(cur, language_id, dialect_id, cat_ids, rows, position_start=0):
    inserted = updated = 0
    for offset, r in enumerate(rows):
        cur.execute(
            """
            INSERT INTO content_items (
                source_key, language_id, dialect_id, category_id,
                content_type, difficulty_level,
                target_text, target_text_toned, english_translation,
                literal_translation, cultural_note,
                example_sentence, example_translation,
                audio_url, audio_state, sort_order
            ) VALUES (
                %(source_key)s, %(language_id)s, %(dialect_id)s, %(category_id)s,
                %(content_type)s, %(difficulty)s,
                %(target_text)s, %(toned)s, %(english)s,
                %(literal)s, %(cultural)s,
                %(example)s, %(example_en)s,
                %(audio_url)s, %(audio_state)s, %(sort_order)s
            )
            ON CONFLICT (source_key) DO UPDATE SET
                category_id         = EXCLUDED.category_id,
                difficulty_level    = EXCLUDED.difficulty_level,
                target_text         = EXCLUDED.target_text,
                english_translation = EXCLUDED.english_translation,
                literal_translation = EXCLUDED.literal_translation,
                cultural_note       = EXCLUDED.cultural_note,
                example_sentence    = EXCLUDED.example_sentence,
                example_translation = EXCLUDED.example_translation,
                sort_order          = EXCLUDED.sort_order,
                -- tone marking and audio are contributor-owned once set:
                -- the seed only fills them, never blanks them.
                target_text_toned = COALESCE(EXCLUDED.target_text_toned,
                                             content_items.target_text_toned),
                audio_url         = COALESCE(EXCLUDED.audio_url,
                                             content_items.audio_url),
                audio_state       = GREATEST(EXCLUDED.audio_state,
                                             content_items.audio_state)
            RETURNING (xmax = 0) AS was_insert
            """,
            {
                "source_key": r["source_key"],
                "language_id": language_id,
                "dialect_id": dialect_id,
                "category_id": cat_ids[r["category_slug"]],
                "content_type": r["content_type"],
                "difficulty": r["difficulty"],
                "target_text": r["target_text"].strip(),
                "toned": nullify(r.get("target_text_toned")),
                "english": r["english_translation"].strip(),
                "literal": nullify(r.get("literal_translation")),
                "cultural": nullify(r.get("cultural_note")),
                "example": nullify(r.get("example_sentence")),
                "example_en": nullify(r.get("example_translation")),
                "audio_url": nullify(r.get("audio_url")),
                "audio_state": "missing",
                "sort_order": position_start + offset,
            },
        )
        if cur.fetchone()["was_insert"]:
            inserted += 1
        else:
            updated += 1
    return inserted, updated


def upsert_tracks(cur, language_id, cat_ids, tracks):
    for t in tracks:
        cur.execute(
            """
            INSERT INTO tracks (language_id, slug, name, description,
                                min_difficulty, max_difficulty, is_default)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (language_id, slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                min_difficulty = EXCLUDED.min_difficulty,
                max_difficulty = EXCLUDED.max_difficulty,
                is_default = EXCLUDED.is_default
            RETURNING id
            """,
            (
                language_id,
                t["slug"],
                t["name"],
                (t.get("description") or "").strip(),
                t.get("min_difficulty", "beginner"),
                t.get("max_difficulty", "native"),
                t.get("is_default", False),
            ),
        )
        track_id = cur.fetchone()["id"]

        # rules and units are fully declared in YAML — replace wholesale
        cur.execute("DELETE FROM track_rules WHERE track_id = %s", (track_id,))
        for rule in t.get("rules", []):
            cur.execute(
                """
                INSERT INTO track_rules (track_id, priority, match_age,
                                         match_connection, match_goal, match_style)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    track_id,
                    rule["priority"],
                    rule.get("match_age"),
                    rule.get("match_connection"),
                    rule.get("match_goal"),
                    rule.get("match_style"),
                ),
            )

        cur.execute("DELETE FROM track_units WHERE track_id = %s", (track_id,))
        for u in t.get("units", []):
            if u["mode"] not in VALID_MODE:
                raise SeedError(f"track {t['slug']}: bad mode {u['mode']!r}")
            cat = u.get("category")
            if cat and cat not in cat_ids:
                raise SeedError(f"track {t['slug']}: unknown category {cat!r}")
            cur.execute(
                """
                INSERT INTO track_units (track_id, position, title, mode,
                                         filter_category_id, filter_content_type,
                                         filter_difficulty, item_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    track_id,
                    u["position"],
                    u["title"],
                    u["mode"],
                    cat_ids[cat] if cat else None,
                    u.get("content_type"),
                    u.get("difficulty"),
                    u.get("item_count", 10),
                ),
            )


# --------------------------------------------------------------------------
# coverage report — catches tracks pointing at empty content sets
# --------------------------------------------------------------------------


def report_coverage(cur, language_id):
    cur.execute(
        """
        SELECT t.slug AS track, u.position, u.title, u.item_count AS requested,
               (SELECT count(*) FROM content_items c
                 WHERE c.language_id = t.language_id
                   AND c.status = 'published'
                   AND (u.filter_category_id  IS NULL OR c.category_id = u.filter_category_id)
                   AND (u.filter_content_type IS NULL OR c.content_type = u.filter_content_type)
                   AND (u.filter_difficulty   IS NULL OR c.difficulty_level = u.filter_difficulty)
               ) AS available
          FROM track_units u
          JOIN tracks t ON t.id = u.track_id
         WHERE t.language_id = %s
         ORDER BY t.slug, u.position
        """,
        (language_id,),
    )
    thin = [r for r in cur.fetchall() if r["available"] < r["requested"]]
    if thin:
        print("\n  Units with fewer items than requested:")
        for r in thin:
            flag = "EMPTY" if r["available"] == 0 else "thin "
            print(
                f"    [{flag}] {r['track']} #{r['position']} {r['title']}: "
                f"{r['available']}/{r['requested']}"
            )
    else:
        print("\n  Coverage: every track unit has enough content.")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def seed_language(conn, code, dry_run=False):
    lang_dir = CONTENT_ROOT / code
    if not lang_dir.is_dir():
        raise SeedError(f"no content directory at {lang_dir}")

    spec = yaml.safe_load((lang_dir / "language.yaml").read_text(encoding="utf-8"))
    lang = spec["language"]
    categories = spec["categories"]
    tone_policy = spec.get("tone_policy", {})
    cat_slugs = {c["slug"] for c in categories}

    # ---- read + validate before touching the database ----
    all_rows, errors, warnings = {}, [], []
    for content_type, filename in CONTENT_FILES.items():
        path = lang_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values())]
        all_rows[content_type] = rows
        e, w = validate_rows(rows, content_type, cat_slugs, tone_policy, path)
        errors += e
        warnings += w

    print(f"\n=== {lang['name']} ({code}) ===")
    for content_type, rows in all_rows.items():
        toned = sum(1 for r in rows if (r.get("target_text_toned") or "").strip())
        print(f"  {content_type:8s} {len(rows):3d} rows   ({toned} tone-marked)")

    for w in warnings:
        print(f"  WARN  {w}")
    if errors:
        for e in errors:
            print(f"  ERROR {e}", file=sys.stderr)
        raise SeedError(f"{len(errors)} validation error(s) — nothing written")

    if dry_run:
        print("  dry run — no writes")
        return

    with conn.cursor(row_factory=dict_row) as cur:
        language_id = upsert_language(cur, lang)
        dialects = upsert_dialects(cur, language_id, spec.get("dialects", []))
        default_dialect = next(
            (d["code"] for d in spec.get("dialects", []) if d.get("is_default")), None
        )
        dialect_id = dialects.get(default_dialect)
        cat_ids = upsert_categories(cur, language_id, categories)

        base = {"word": 0, "phrase": 1000, "proverb": 2000}
        totals = [0, 0]
        for content_type, rows in all_rows.items():
            ins, upd = upsert_content(
                cur, language_id, dialect_id, cat_ids, rows, base[content_type]
            )
            totals[0] += ins
            totals[1] += upd
        print(f"  content: {totals[0]} inserted, {totals[1]} updated")

        tracks = yaml.safe_load((lang_dir / "tracks.yaml").read_text(encoding="utf-8"))
        upsert_tracks(cur, language_id, cat_ids, tracks["tracks"])
        print(f"  tracks:  {len(tracks['tracks'])} upserted")

        report_coverage(cur, language_id)

    conn.commit()


def main():
    ap = argparse.ArgumentParser(description="Seed Jalɛ content.")
    ap.add_argument("--language", "-l", help="language code, e.g. ibo")
    ap.add_argument("--all", action="store_true", help="seed every content/<code>/")
    ap.add_argument("--dry-run", action="store_true", help="validate only")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()

    if not args.language and not args.all:
        ap.error("pass --language <code> or --all")
    if not args.database_url and not args.dry_run:
        ap.error("set DATABASE_URL or pass --database-url")

    codes = (
        sorted(p.name for p in CONTENT_ROOT.iterdir() if p.is_dir())
        if args.all
        else [args.language]
    )

    conn = None if args.dry_run else psycopg.connect(args.database_url)
    try:
        for code in codes:
            seed_language(conn, code, dry_run=args.dry_run)
    except SeedError as exc:
        print(f"\nseed failed: {exc}", file=sys.stderr)
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if conn:
            conn.close()
    print("\ndone.\n")


if __name__ == "__main__":
    main()
