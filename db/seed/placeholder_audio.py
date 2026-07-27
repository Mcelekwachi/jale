#!/usr/bin/env python3
"""
Jalɛ — placeholder audio generator.

Every content item needs a play button from day one, even before a native
speaker has recorded anything. This writes one audio file per item and sets
audio_state='placeholder'. Real recordings later overwrite audio_url and set
audio_state='verified' — no schema change, no code change.

    python db/seed/placeholder_audio.py --language ibo --engine silence
    python db/seed/placeholder_audio.py --language ibo --engine gtts

Engines
    silence  stdlib only, zero dependencies, produces a valid short WAV.
             Use this to build and test the UI.
    gtts     Google TTS via `pip install gtts`. Yoruba-accented approximation
             of Igbo — good enough to check timing and UX, never good enough
             to ship to a native speaker. Marked 'placeholder' either way.

Never overwrites an item whose audio_state is already 'verified'.
"""

from __future__ import annotations

import argparse
import os
import sys
import wave
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "audio"


def write_silence(path: Path, seconds: float = 0.6, rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


def write_gtts(path: Path, text: str) -> None:
    from gtts import gTTS  # optional dependency

    path.parent.mkdir(parents=True, exist_ok=True)
    # No Igbo voice exists; Yoruba is the closest available approximation.
    gTTS(text=text, lang="yo").save(str(path))


def main():
    ap = argparse.ArgumentParser(description="Generate placeholder audio.")
    ap.add_argument("--language", "-l", required=True)
    ap.add_argument("--engine", choices=["silence", "gtts"], default="silence")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--url-prefix", default="/audio")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()

    if not args.database_url:
        ap.error("set DATABASE_URL or pass --database-url")

    ext = "wav" if args.engine == "silence" else "mp3"

    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.source_key, c.target_text
                  FROM content_items c JOIN languages l ON l.id = c.language_id
                 WHERE l.code = %s AND c.audio_state <> 'verified'
                 ORDER BY c.sort_order
                """,
                (args.language,),
            )
            rows = cur.fetchall()

            if not rows:
                print("nothing to generate — all items already have verified audio")
                return

            made = 0
            for r in rows:
                slug = r["source_key"].replace(":", "_")
                fname = f"{slug}.{ext}"
                target = args.out_dir / args.language / fname
                try:
                    if args.engine == "silence":
                        write_silence(target)
                    else:
                        write_gtts(target, r["target_text"])
                except Exception as exc:  # keep going; report at the end
                    print(f"  skip {r['source_key']}: {exc}", file=sys.stderr)
                    continue

                cur.execute(
                    """
                    UPDATE content_items
                       SET audio_url = %s, audio_state = 'placeholder'
                     WHERE id = %s
                    """,
                    (f"{args.url_prefix}/{args.language}/{fname}", r["id"]),
                )
                made += 1
        conn.commit()

    print(f"{made} placeholder files -> {args.out_dir / args.language}")
    print(
        "run export_worklist.py --task audio to get the recording list for your next Nigeria trip"
    )


if __name__ == "__main__":
    main()
