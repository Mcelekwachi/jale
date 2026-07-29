#!/usr/bin/env python3
"""
Jalɛ — contributor worklist exporter.

Produces CSVs you can hand to a native-speaker contributor (on a laptop in
Arochukwu, offline, in Excel) and re-import through seed.py afterwards.

    python db/seed/export_worklist.py --language ibo --task tone
    python db/seed/export_worklist.py --language ibo --task audio
    python db/seed/export_worklist.py --language ibo --task flagged

Round trip:
    1. export  -> worklists/ibo_tone_<date>.csv
    2. contributor fills target_text_toned column only
    3. paste that column back into content/ibo/proverbs.csv (keyed by source_key)
    4. python db/seed/seed.py --language ibo
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

OUT_DIR = Path(__file__).resolve().parents[2] / "worklists"

QUERIES = {
    # items inside the language's tone policy that nobody has marked yet
    "tone": """
        SELECT c.source_key, c.content_type, cat.slug AS category,
               c.target_text, c.target_text_toned, ct.translation
          FROM content_items c
          JOIN languages l ON l.id = c.language_id
          JOIN content_translations ct ON ct.content_id = c.id
          JOIN languages ml ON ml.id = ct.meta_language_id
     LEFT JOIN categories cat ON cat.id = c.category_id
         WHERE l.code = %(code)s
           AND ml.code = %(meta_language)s
           AND c.content_type IN ('phrase', 'proverb')
           AND c.target_text_toned IS NULL
           AND c.status = 'published'
      ORDER BY c.content_type, c.sort_order
    """,
    # every item that has no real recording yet
    "audio": """
        SELECT c.source_key, c.content_type, cat.slug AS category,
               c.target_text, ct.translation,
               c.audio_state, c.audio_url
          FROM content_items c
          JOIN languages l ON l.id = c.language_id
          JOIN content_translations ct ON ct.content_id = c.id
          JOIN languages ml ON ml.id = ct.meta_language_id
     LEFT JOIN categories cat ON cat.id = c.category_id
         WHERE l.code = %(code)s
           AND ml.code = %(meta_language)s
           AND c.audio_state <> 'verified'
           AND c.status = 'published'
      ORDER BY c.content_type, c.sort_order
    """,
    # translations and cultural notes awaiting a native speaker's sign-off
    "verify": """
        SELECT c.source_key, c.content_type, c.target_text,
               ct.translation, ct.literal_translation, ct.cultural_note, ct.verified
          FROM content_items c
          JOIN languages l ON l.id = c.language_id
          JOIN content_translations ct ON ct.content_id = c.id
          JOIN languages ml ON ml.id = ct.meta_language_id
         WHERE l.code = %(code)s
           AND ml.code = %(meta_language)s
           AND ct.verified = FALSE
           AND c.status = 'published'
      ORDER BY c.content_type, c.sort_order
    """,
    # what users have reported, worst first
    "flagged": """
        SELECT c.id AS content_id, c.content_type, c.target_text,
               ml.code AS meta_language, ct.translation, ct.literal_translation,
               ct.cultural_note, ct.verified, count(*)::int AS flag_count,
               min(f.created_at) AS oldest_flag_at,
               array_to_string(array_agg(DISTINCT f.reason), '; ') AS reasons
          FROM content_flags f
          JOIN content_items c ON c.id = f.content_id
          JOIN languages l ON l.id = c.language_id
     LEFT JOIN languages ml ON ml.id = f.meta_language_id
     LEFT JOIN content_translations ct
            ON ct.content_id = c.id AND ct.meta_language_id = f.meta_language_id
         WHERE l.code = %(code)s
           AND f.status IN ('open', 'in_review')
      GROUP BY c.id, c.content_type, c.target_text, ml.code, ct.translation,
               ct.literal_translation, ct.cultural_note, ct.verified
      ORDER BY flag_count DESC, oldest_flag_at ASC
    """,
}


def main():
    ap = argparse.ArgumentParser(description="Export a contributor worklist.")
    ap.add_argument("--language", "-l", required=True)
    ap.add_argument("--task", "-t", required=True, choices=sorted(QUERIES))
    ap.add_argument("--out", help="output path (default: worklists/<lang>_<task>_<date>.csv)")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--meta-language", default=os.environ.get("DEFAULT_META_LANGUAGE", "eng"))
    args = ap.parse_args()

    if not args.database_url:
        ap.error("set DATABASE_URL or pass --database-url")

    with psycopg.connect(args.database_url) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            QUERIES[args.task],
            {"code": args.language, "meta_language": args.meta_language},
        )
        rows = cur.fetchall()

    if not rows:
        print(f"nothing outstanding for {args.language}/{args.task}")
        return

    out = (
        Path(args.out)
        if args.out
        else (OUT_DIR / f"{args.language}_{args.task}_{date.today():%Y%m%d}.csv")
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
