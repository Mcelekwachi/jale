#!/usr/bin/env python3
"""Discover public recordings and attach them to published content items."""

from __future__ import annotations

import argparse
import csv
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row

CONTENT_QUERY = """
    SELECT c.id, c.source_key, c.content_type, c.target_text,
           default_ct.translation, c.audio_url, c.audio_state
      FROM content_items c
      JOIN languages l ON l.id = c.language_id
 LEFT JOIN languages default_ml ON default_ml.code = 'eng'
 LEFT JOIN content_translations default_ct
        ON default_ct.content_id = c.id
       AND default_ct.meta_language_id = default_ml.id
     WHERE l.code = %s
       AND c.status = 'published'
  ORDER BY c.content_type, c.sort_order, c.id
"""

UPDATE_QUERY = """
    UPDATE content_items
       SET audio_url = %s, audio_state = %s
     WHERE id = %s
"""

WORKLIST_FIELDS = [
    "source_key",
    "content_type",
    "target_text",
    "translation",
    "filename",
]


@dataclass(frozen=True)
class ImportOptions:
    language: str
    bucket: str = "audio"
    folder: str = "Igbo"
    extension: str = "mp3"
    base_url: str = ""
    audio_state: str = "verified"
    dry_run: bool = False
    export_worklist: Path | None = None


@dataclass
class ImportResult:
    total_items: int = 0
    recordings_found: int = 0
    newly_linked: int = 0
    already_linked: int = 0
    missing: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    unexpected_urls: list[tuple[str, str]] = field(default_factory=list)


def filename_for(source_key: str, extension: str) -> str:
    return f"{source_key.replace(':', '_')}.{extension.lstrip('.')}"


def public_url(options: ImportOptions, source_key: str) -> str:
    filename = filename_for(source_key, options.extension)
    return (
        f"{options.base_url.rstrip('/')}/storage/v1/object/public/"
        f"{options.bucket}/{options.folder}/{filename}"
    )


def head_exists(url: str) -> bool:
    request = Request(url, method="HEAD")
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            if response.status == 200:
                return True
            raise RuntimeError(f"unexpected HTTP {response.status} for {url}")
    except HTTPError as exc:
        if exc.code in {400, 404}:
            return False
        raise


def write_worklist(path: Path, rows: list[dict], options: ImportOptions) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKLIST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source_key": row["source_key"],
                    "content_type": row["content_type"],
                    "target_text": row["target_text"],
                    "translation": row["translation"] or "",
                    "filename": filename_for(row["source_key"], options.extension),
                }
            )


def run_import(conn, options: ImportOptions, *, head_exists=head_exists) -> ImportResult:
    with conn.cursor() as cursor:
        cursor.execute(CONTENT_QUERY, (options.language,))
        rows = cursor.fetchall()

    expected_urls = [public_url(options, row["source_key"]) for row in rows]
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = list(pool.map(head_exists, expected_urls))

    result = ImportResult(
        total_items=len(rows),
        recordings_found=sum(found),
    )
    updates = []
    missing_rows = []

    for row, expected_url, recording_found in zip(rows, expected_urls, found, strict=True):
        existing_url = row["audio_url"]
        if existing_url and existing_url != expected_url:
            result.unexpected_urls.append((row["source_key"], existing_url))

        if not recording_found:
            result.missing.append(row["source_key"])
            missing_rows.append(row)
            continue

        existing_state = row["audio_state"]
        if existing_url and existing_url != expected_url:
            continue

        new_state = "verified" if existing_state == "verified" else options.audio_state
        if existing_url == expected_url and existing_state == new_state:
            result.already_linked += 1
            continue

        result.newly_linked += 1
        result.changes.append(row["source_key"])
        updates.append((expected_url, new_state, row["id"]))

    if options.export_worklist:
        write_worklist(options.export_worklist, missing_rows, options)

    if not options.dry_run and updates:
        with conn.transaction(), conn.cursor() as cursor:
            for update in updates:
                cursor.execute(UPDATE_QUERY, update)

    return result


def print_report(result: ImportResult, *, dry_run: bool) -> None:
    print("\nAudio import summary")
    print(f"{'total items':<20} {result.total_items}")
    print(f"{'recordings found':<20} {result.recordings_found}")
    print(f"{'newly linked':<20} {result.newly_linked}")
    print(f"{'already linked':<20} {result.already_linked}")
    print(f"{'MISSING':<20} {len(result.missing)}")

    if dry_run and result.changes:
        print("\nWould link:")
        for source_key in result.changes:
            print(f"  {source_key}")

    print("\nMissing source keys:")
    for source_key in result.missing:
        print(f"  {source_key}")

    if result.unexpected_urls:
        print("\nUnexpected existing audio URLs (not changed):")
        for source_key, url in result.unexpected_urls:
            print(f"  {source_key}: {url}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import public audio recordings.")
    parser.add_argument("--language", "-l", required=True)
    parser.add_argument("--bucket", default="audio")
    parser.add_argument("--folder", default="Igbo")
    parser.add_argument("--extension", default="mp3")
    parser.add_argument("--base-url", default=os.environ.get("SUPABASE_PROJECT_URL"))
    parser.add_argument("--audio-state", choices=["verified", "placeholder"], default="verified")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--export-worklist", type=Path)
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("set DATABASE_URL or pass --database-url")
    if not args.base_url:
        parser.error("set SUPABASE_PROJECT_URL or pass --base-url")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    options = ImportOptions(
        language=args.language,
        bucket=args.bucket,
        folder=args.folder,
        extension=args.extension,
        base_url=args.base_url,
        audio_state=args.audio_state,
        dry_run=args.dry_run,
        export_worklist=args.export_worklist,
    )
    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        result = run_import(conn, options)
    print_report(result, dry_run=args.dry_run)
    if args.export_worklist:
        print(f"\n{len(result.missing)} rows -> {args.export_worklist}")


if __name__ == "__main__":
    main()
