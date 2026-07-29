# Meta-Language Content Translations Design

## Objective

Move learner-facing explanations out of `content_items` and into translations keyed by a shared meta-language. Preserve all current API behavior except for renaming `english_translation` to `translation` and adding `meta_language`, while making future explanation languages content-only additions.

## Schema

`languages` remains the single language registry and gains `is_learnable` and `is_meta`, both non-null booleans defaulting to false. The repository uses a fresh-schema bootstrap rather than versioned migrations, so `db/schema.sql` will be edited in place rather than adding `ALTER TABLE` migration files.

`content_translations` will use `(content_id, meta_language_id)` as its primary key. It owns `translation`, `literal_translation`, `cultural_note`, verification metadata, contributor metadata, and timestamps. Its content foreign key cascades on deletion; its language and contributor foreign keys follow the requested references. The three explanation columns will be removed from `content_items`.

A `BEFORE INSERT OR UPDATE` trigger on `content_translations` will look up the parent content type and reject a proverb translation whose `cultural_note` is null. This replaces the cross-entity invariant formerly expressed as a `content_items` check.

`content_flags.meta_language_id` will be nullable. Null denotes an item-level flag; a value denotes a translation-level flag. The partial open-flag uniqueness index will key on `(content_id, user_id, COALESCE(meta_language_id, 0))`.

## Content and Seeding

`content/meta_languages.yaml` will define English (`eng`) and Dutch (`nld`) as active meta-languages that are not learnable. The three Igbo source CSVs will retain only `source_key`, `content_type`, `category_slug`, `difficulty`, `target_text`, and `target_text_toned`.

Every existing explanation value will be moved character-for-character into `content/ibo/translations/en.csv`. `nl.csv` will contain the same 157 source keys with empty explanation fields. No Igbo text, tones, categories, difficulty values, or keys will change.

The seed loader will upsert meta-languages, then content items, then every translation CSV discovered below each target language. It will map the translation filename to an ISO 639-3 meta-language code, resolve each source key to its content ID, skip rows with an empty `translation`, and upsert by `(content_id, meta_language_id)`. Conflict updates will use existing nonblank values when an incoming optional value is blank, matching the current protection for toned text and audio. Before writes, validation will require every proverb to have a non-empty English cultural note and will emit a readable source-specific error.

## API and Worklists

Configuration gains `DEFAULT_META_LANGUAGE`, defaulting to `eng`. Content and study SQL will join exactly one `content_translations` row using that language code. There will be no request parameter, fallback, study-direction change, or additional language behavior.

Responses will expose `translation` and `meta_language`; `english_translation` will disappear. Existing literal-translation and cultural-note behavior remains. Content search will search the joined default translation. Worklist queries will read explanation and verification fields from `content_translations`, associating translation-specific flags where applicable.

## Validation and Tests

Tests will first establish the new behavior: the proverb trigger rejects a missing cultural note, seeding creates 157 English and zero Dutch translation rows, and a user may hold one item-level and one translation-level open flag for the same content item while duplicates at either scope are rejected. Existing API assertions will be updated for `translation` and `meta_language`.

Completion requires all 33 tests to pass plus successful runs of:

- `pytest -q`
- `ruff check backend db`
- `python db/seed/seed.py --all --dry-run`

The final report will include the fresh-schema approach, the complete trigger definition, seeded row counts, and the exact verification results.

## Explicit Non-Goals

No meta-language request parameter, fallback logic, study direction, persona-enum change, Yoruba content, or second target language will be added.
