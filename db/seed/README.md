# Seed tooling

```bash
pip install -r db/seed/requirements.txt
export DATABASE_URL=postgresql://...

psql "$DATABASE_URL" -f db/schema.sql       # once
python db/seed/seed.py --language ibo       # idempotent, run on every deploy
python db/seed/placeholder_audio.py -l ibo --engine silence
```

## Contributor round trip

```bash
python db/seed/export_worklist.py -l ibo -t tone     # 100 phrases + proverbs
python db/seed/export_worklist.py -l ibo -t audio    # recording list
python db/seed/export_worklist.py -l ibo -t verify   # translation sign-off
python db/seed/export_worklist.py -l ibo -t flagged  # what users reported
```

The contributor edits one column in Excel. Paste it back into the matching
`content/ibo/*.csv` on `source_key`, re-run `seed.py`, done.

## Guarantees

- Keyed on `source_key`; re-running never duplicates and never touches
  `user_progress`, `user_daily_activity`, `user_stats` or `content_flags`.
- `target_text_toned` and `audio_url` are contributor-owned once set: the
  seed fills them when blank, never blanks them.
- Validation runs before any write. One bad row means zero rows written.
- `--dry-run` validates without a database connection.

## Adding a language

```bash
mkdir content/yor
cp content/ibo/language.yaml content/ibo/tracks.yaml content/yor/
# edit those two, add words.csv / phrases.csv / proverbs.csv
python db/seed/seed.py --language yor
```

No new tables, no new columns, no application code.
