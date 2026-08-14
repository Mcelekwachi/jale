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
TARGET_HEADERS = {
    "source_key",
    "content_type",
    "target_text",
    "target_text_toned",
    "category_slug",
    "difficulty",
}
TRANSLATION_HEADERS = {
    "source_key",
    "translation",
    "literal_translation",
    "cultural_note",
}


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

        if r.get("category_slug") not in categories:
            errors.append(f"{loc} unknown category {r.get('category_slug')!r}")

        if r.get("difficulty") not in VALID_DIFFICULTY:
            errors.append(f"{loc} bad difficulty {r.get('difficulty')!r}")

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
        INSERT INTO languages (code, name, endonym, flag_emoji, is_active,
                               is_learnable, is_meta, required_validators, sort_order)
        VALUES (%(code)s, %(name)s, %(endonym)s, %(flag_emoji)s,
                %(is_active)s, %(is_learnable)s, %(is_meta)s,
                %(required_validators)s, %(sort_order)s)
        ON CONFLICT (code) DO UPDATE SET
            name       = COALESCE(NULLIF(EXCLUDED.name, ''), languages.name),
            endonym    = COALESCE(NULLIF(EXCLUDED.endonym, ''), languages.endonym),
            flag_emoji = COALESCE(NULLIF(EXCLUDED.flag_emoji, ''), languages.flag_emoji),
            is_active  = EXCLUDED.is_active,
            is_learnable = EXCLUDED.is_learnable,
            is_meta      = EXCLUDED.is_meta,
            required_validators = EXCLUDED.required_validators,
            sort_order = EXCLUDED.sort_order
        RETURNING id
        """,
        {
            "code": lang["code"],
            "name": lang["name"],
            "endonym": lang.get("endonym"),
            "flag_emoji": lang.get("flag_emoji"),
            "is_active": lang.get("is_active", False),
            "is_learnable": lang.get("is_learnable", False),
            "is_meta": lang.get("is_meta", False),
            "required_validators": lang.get("required_validators", 1),
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
            SELECT c.language_id, l.code AS language_code, c.content_type
              FROM content_items c
              JOIN languages l ON l.id = c.language_id
             WHERE c.source_key = %s
            """,
            (r["source_key"],),
        )
        owner = cur.fetchone()
        if owner and (
            owner["language_id"] != language_id or owner["content_type"] != r["content_type"]
        ):
            raise SeedError(
                f"source_key {r['source_key']!r} ownership mismatch: existing "
                f"language={owner['language_code']!r}, content_type="
                f"{owner['content_type']!r}; incoming language_id={language_id}, "
                f"content_type={r['content_type']!r}"
            )
        cur.execute(
            """
            INSERT INTO content_items (
                source_key, language_id, dialect_id, category_id,
                content_type, difficulty_level,
                target_text, target_text_toned, example_sentence,
                audio_url, audio_state, sort_order
            ) VALUES (
                %(source_key)s, %(language_id)s, %(dialect_id)s, %(category_id)s,
                %(content_type)s, %(difficulty)s,
                %(target_text)s, %(toned)s, %(example)s,
                %(audio_url)s, %(audio_state)s, %(sort_order)s
            )
            ON CONFLICT (source_key) DO UPDATE SET
                category_id         = EXCLUDED.category_id,
                difficulty_level    = EXCLUDED.difficulty_level,
                target_text         = EXCLUDED.target_text,
                example_sentence    = EXCLUDED.example_sentence,
                sort_order          = EXCLUDED.sort_order,
                -- tone marking and audio are contributor-owned once set:
                -- the seed only fills them, never blanks them.
                target_text_toned = COALESCE(EXCLUDED.target_text_toned,
                                             content_items.target_text_toned),
                audio_url         = COALESCE(EXCLUDED.audio_url,
                                             content_items.audio_url),
                audio_state       = GREATEST(EXCLUDED.audio_state,
                                             content_items.audio_state)
            WHERE content_items.language_id = EXCLUDED.language_id
              AND content_items.content_type = EXCLUDED.content_type
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
                "example": nullify(r.get("example_sentence")),
                "audio_url": nullify(r.get("audio_url")),
                "audio_state": "missing",
                "sort_order": position_start + offset,
            },
        )
        result = cur.fetchone()
        if result is None:
            raise SeedError(
                f"source_key {r['source_key']!r} ownership changed during upsert; "
                "existing language/content_type was not modified"
            )
        if result["was_insert"]:
            inserted += 1
        else:
            updated += 1
    return inserted, updated


def upsert_translations(cur, content_ids, language_ids, translations):
    inserted = updated = 0
    for row in translations:
        cur.execute(
            """
            INSERT INTO content_translations (
                content_id, meta_language_id, translation,
                literal_translation, cultural_note
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (content_id, meta_language_id) DO UPDATE SET
                translation = COALESCE(NULLIF(EXCLUDED.translation, ''),
                                       content_translations.translation),
                literal_translation = COALESCE(EXCLUDED.literal_translation,
                                               content_translations.literal_translation),
                cultural_note = COALESCE(EXCLUDED.cultural_note,
                                         content_translations.cultural_note)
            RETURNING (xmax = 0) AS was_insert
            """,
            (
                content_ids[row["source_key"]],
                language_ids[row["meta_code"]],
                row["translation"],
                row["literal_translation"],
                row["cultural_note"],
            ),
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


def read_csv(path, required_headers, errors):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = sorted(required_headers - set(reader.fieldnames or []))
        if missing:
            errors.append(f"{path}: missing required header(s): {', '.join(missing)}")
        return [r for r in reader if any((v or "").strip() for v in r.values())]


def load_language_registry(errors):
    path = CONTENT_ROOT / "languages.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        errors.append(f"{path}: YAML root must be a mapping")
        return [], {}
    languages = document.get("languages")
    if not isinstance(languages, list):
        errors.append(f"{path}: top-level 'languages' must be a list")
        return [], {}
    file_codes, codes = {}, set()
    for index, lang in enumerate(languages, start=1):
        loc = f"{path}:languages[{index}]"
        if not isinstance(lang, dict):
            errors.append(f"{loc}: language entry must be a mapping")
            continue
        lang.setdefault("required_validators", 1)
        for field in (
            "code",
            "name",
            "endonym",
            "flag_emoji",
            "is_active",
            "is_learnable",
            "is_meta",
            "sort_order",
        ):
            value = lang.get(field)
            if field not in lang or value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{loc}: missing {field}")
        code, file_code = lang.get("code"), lang.get("file_code")
        if code in codes:
            errors.append(f"{loc}: duplicate language code {code!r}")
        codes.add(code)
        if lang.get("is_meta") and not file_code:
            errors.append(f"{loc}: meta language is missing file_code")
        if file_code in file_codes:
            errors.append(f"{loc}: duplicate file_code {file_code!r}")
        elif file_code:
            file_codes[file_code] = code
        if not lang.get("is_meta", False) and not lang.get("is_learnable", False):
            errors.append(f"{loc}: language must be learnable, meta, or both")
        threshold = lang.get("required_validators")
        if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 1:
            errors.append(f"{loc}: required_validators must be a positive integer")
    return languages, file_codes


def prepare_language(code, file_codes):
    lang_dir = CONTENT_ROOT / code
    if not lang_dir.is_dir():
        raise SeedError(f"no content directory at {lang_dir}")

    spec = yaml.safe_load((lang_dir / "language.yaml").read_text(encoding="utf-8"))
    lang = spec["language"]
    categories = spec["categories"]
    tone_policy = spec.get("tone_policy", {})
    cat_slugs = {c["slug"] for c in categories}

    # ---- read + validate before touching the database ----
    all_rows, errors, warnings, source_types = {}, [], [], {}
    for content_type, filename in CONTENT_FILES.items():
        path = lang_dir / filename
        if not path.exists():
            continue
        rows = read_csv(path, TARGET_HEADERS, errors)
        all_rows[content_type] = rows
        e, w = validate_rows(rows, content_type, cat_slugs, tone_policy, path)
        errors += e
        warnings += w
        for row in rows:
            key = row.get("source_key")
            if key in source_types:
                errors.append(f"{path}: duplicate source_key {key!r} across content files")
            elif key:
                source_types[key] = content_type

    translations = []
    english_proverb_rows = set()
    translation_dir = lang_dir / "translations"
    paths = sorted(translation_dir.glob("*.csv")) if translation_dir.is_dir() else []
    for path in paths:
        meta_code = file_codes.get(path.stem)
        if not meta_code:
            errors.append(
                f"{path}: filename code {path.stem!r} is not declared as file_code "
                "in content/languages.yaml"
            )
        rows = read_csv(path, TRANSLATION_HEADERS, errors)
        seen = set()
        for line, row in enumerate(rows, start=2):
            key = (row.get("source_key") or "").strip()
            loc = f"{path}:{line}"
            if not key:
                errors.append(f"{loc}: missing source_key")
                continue
            if key in seen:
                errors.append(f"{loc}: duplicate source_key {key!r}")
            seen.add(key)
            if key not in source_types:
                errors.append(f"{loc}: unknown source_key {key!r}")
            translation = nullify(row.get("translation"))
            cultural_note = nullify(row.get("cultural_note"))
            if meta_code == "eng" and source_types.get(key) == "proverb":
                english_proverb_rows.add(key)
                if not translation:
                    errors.append(f"{loc}: proverb {key!r} missing translation")
                if not cultural_note:
                    errors.append(f"{loc}: proverb {key!r} missing cultural_note")
            if translation:
                translations.append(
                    {
                        "source_key": key,
                        "meta_code": meta_code,
                        "translation": translation,
                        "literal_translation": nullify(row.get("literal_translation")),
                        "cultural_note": cultural_note,
                    }
                )

    english_file_code = next(
        (file_code for file_code, meta_code in file_codes.items() if meta_code == "eng"),
        "eng",
    )
    english_path = translation_dir / f"{english_file_code}.csv"
    for key, content_type in source_types.items():
        if content_type == "proverb" and key not in english_proverb_rows:
            errors.append(f"{english_path}: proverb {key!r} missing translation")
            errors.append(f"{english_path}: proverb {key!r} missing cultural_note")

    tracks_path = lang_dir / "tracks.yaml"
    tracks_document = yaml.safe_load(tracks_path.read_text(encoding="utf-8")) or {}
    tracks = tracks_document.get("tracks")
    if not isinstance(tracks, list):
        errors.append(f"{tracks_path}: top-level 'tracks' must be a list")
        tracks = []
    for track in tracks:
        track_loc = f"{tracks_path}: track {track.get('slug')!r}"
        for unit in track.get("units", []):
            if unit.get("mode") not in VALID_MODE:
                errors.append(f"{track_loc}: bad mode {unit.get('mode')!r}")
            category = unit.get("category")
            if category and category not in cat_slugs:
                errors.append(f"{track_loc}: unknown category {category!r}")

    print(f"\n=== {lang['name']} ({code}) ===")
    for content_type, rows in all_rows.items():
        toned = sum(1 for r in rows if (r.get("target_text_toned") or "").strip())
        print(f"  {content_type:8s} {len(rows):3d} rows   ({toned} tone-marked)")

    for w in warnings:
        print(f"  WARN  {w}")
    if errors:
        return None, errors
    return {
        "spec": spec,
        "code": code,
        "lang": lang,
        "categories": categories,
        "all_rows": all_rows,
        "translations": translations,
        "source_keys": set(source_types),
        "lang_dir": lang_dir,
        "tracks": tracks,
    }, []


def write_registry(conn, registry):
    with conn.cursor(row_factory=dict_row) as cur:
        for language in registry:
            upsert_language(cur, language)


def write_language(conn, plan, registry_by_code):
    spec, lang = plan["spec"], plan["lang"]
    categories, all_rows = plan["categories"], plan["all_rows"]
    with conn.cursor(row_factory=dict_row) as cur:
        merged_language = {**registry_by_code[lang["code"]], **lang}
        language_id = upsert_language(cur, merged_language)
        cur.execute("SELECT code, id FROM languages WHERE is_meta")
        language_ids = {row["code"]: row["id"] for row in cur.fetchall()}
        dialects = upsert_dialects(cur, language_id, spec.get("dialects", []))
        default_dialect = next(
            (d["code"] for d in spec.get("dialects", []) if d.get("is_default")), None
        )
        cat_ids = upsert_categories(cur, language_id, categories)
        base = {"word": 0, "phrase": 1000, "proverb": 2000}
        totals = [0, 0]
        for content_type, rows in all_rows.items():
            ins, upd = upsert_content(
                cur,
                language_id,
                dialects.get(default_dialect),
                cat_ids,
                rows,
                base[content_type],
            )
            totals[0] += ins
            totals[1] += upd
        print(f"  content: {totals[0]} inserted, {totals[1]} updated")
        cur.execute(
            "SELECT source_key, id FROM content_items WHERE source_key = ANY(%s)",
            (list(plan["source_keys"]),),
        )
        content_ids = {row["source_key"]: row["id"] for row in cur.fetchall()}
        ins, upd = upsert_translations(cur, content_ids, language_ids, plan["translations"])
        print(f"  translations: {ins} inserted, {upd} updated")
        upsert_tracks(cur, language_id, cat_ids, plan["tracks"])
        print(f"  tracks:  {len(plan['tracks'])} upserted")
        report_coverage(cur, language_id)


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

    errors = []
    try:
        registry, file_codes = load_language_registry(errors)
    except (OSError, TypeError, yaml.YAMLError) as exc:
        registry, file_codes = [], {}
        errors.append(f"{CONTENT_ROOT / 'languages.yaml'}: {exc}")
    registry_by_code = {language["code"]: language for language in registry}
    plans = []
    for code in codes:
        try:
            plan, language_errors = prepare_language(code, file_codes)
            errors.extend(language_errors)
            if plan:
                if plan["code"] not in registry_by_code:
                    errors.append(
                        f"content/{code}: language is missing from content/languages.yaml"
                    )
                plans.append(plan)
        except (OSError, KeyError, TypeError, yaml.YAMLError, SeedError) as exc:
            errors.append(f"{CONTENT_ROOT / code}: {exc}")
    source_key_owners = {}
    for plan in plans:
        for source_key in plan["source_keys"]:
            owner = source_key_owners.get(source_key)
            if owner is not None:
                errors.append(
                    f"content/{plan['code']}: source_key {source_key!r} collides with "
                    f"content/{owner}; source_key must be globally unique"
                )
            else:
                source_key_owners[source_key] = plan["code"]
    if errors:
        for error in errors:
            print(f"  ERROR {error}", file=sys.stderr)
        print(
            f"\nseed failed: {len(errors)} validation error(s) — nothing written",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.dry_run:
        print("\ndry run — all content valid; no database connection or writes")
        print("\ndone.\n")
        return

    conn = psycopg.connect(args.database_url)
    try:
        write_registry(conn, registry)
        for plan in plans:
            write_language(conn, plan, registry_by_code)
        conn.commit()
    except SeedError as exc:
        print(f"\nseed failed: {exc}", file=sys.stderr)
        if conn:
            conn.rollback()
        sys.exit(1)
    except Exception:
        conn.rollback()
        raise
    finally:
        if conn:
            conn.close()
    print("\ndone.\n")


if __name__ == "__main__":
    main()
