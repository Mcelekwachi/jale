# Meta-Language Content Translations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store explanations in meta-language translation rows while preserving current content and study behavior through the default English meta-language.

**Architecture:** Keep `languages` as the shared target/meta registry, add `content_translations` beside language-neutral `content_items`, and resolve one configured meta-language in existing SQL joins. Seed target content and translation files separately using natural-key upserts and validate English proverb notes before any write.

**Tech Stack:** PostgreSQL 15, Python 3.12, psycopg 3, FastAPI, Pydantic, pytest, Ruff, YAML/CSV content files.

---

## File Map

- Modify `db/schema.sql`: language roles, translations table, proverb trigger, scoped flags, views.
- Modify `db/seed/seed.py`: meta-language loading, split content/translation validation and upserts.
- Modify `db/seed/export_worklist.py`: translation-owned verification and explanation fields.
- Create `content/meta_languages.yaml`: English and Dutch shared metadata.
- Modify `content/ibo/{words,phrases,proverbs}.csv`: language-neutral target columns only.
- Create `content/ibo/translations/{en,nl}.csv`: moved English data and empty Dutch template.
- Modify `backend/app/config.py`: default meta-language setting.
- Modify `backend/app/{schemas.py,routers/content.py,services/study.py}`: generic response name and default translation join.
- Modify `backend/tests/test_api.py`: API rename and database invariants.

### Task 1: Establish failing database and API tests

**Files:**
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Rename existing API assertions**

Replace response access to `english_translation` with `translation`, assert returned content has `meta_language == "eng"`, and keep the existing search expectation unchanged semantically.

- [ ] **Step 2: Add the database invariant tests**

Add async tests using the existing seeded database fixture and psycopg connections which:

```python
def test_seeded_translation_counts(database_url):
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT l.code, count(ct.content_id)
              FROM languages l
              LEFT JOIN content_translations ct ON ct.meta_language_id = l.id
             WHERE l.code IN ('eng', 'nld')
             GROUP BY l.code
            """
        ).fetchall()
    assert dict(rows) == {"eng": 157, "nld": 0}
```

Add a transaction-isolated proverb insert followed by an invalid translation insert and assert `psycopg.errors.RaiseException` with a readable cultural-note message. Add a user/content fixture inside a rolled-back transaction, insert one null-scope and one English-scope open flag, and assert both succeed while duplicates raise `UniqueViolation`.

- [ ] **Step 3: Run the new tests and verify RED**

Run: `pytest -q backend/tests/test_api.py`

Expected: failures because `content_translations`, `meta_language`, and `translation` do not yet exist.

### Task 2: Move content without changing its characters

**Files:**
- Create: `content/meta_languages.yaml`
- Modify: `content/ibo/words.csv`
- Modify: `content/ibo/phrases.csv`
- Modify: `content/ibo/proverbs.csv`
- Create: `content/ibo/translations/en.csv`
- Create: `content/ibo/translations/nl.csv`

- [ ] **Step 1: Snapshot existing content fields in memory and mechanically split CSVs**

Use a one-off formatting script/PowerShell CSV transformation to write target CSV headers exactly as:

```text
source_key,content_type,category_slug,difficulty,target_text,target_text_toned
```

Write `en.csv` headers exactly as:

```text
source_key,translation,literal_translation,cultural_note
```

Copy each row's `english_translation`, `literal_translation`, and `cultural_note` values without editing them. Write `nl.csv` with all source keys and the other three cells empty.

- [ ] **Step 2: Add shared meta-language metadata**

Create YAML entries for `eng`/English and `nld`/Dutch with `is_meta: true`, `is_learnable: false`, and `is_active: true`.

- [ ] **Step 3: Verify the mechanical move**

Run a read-only comparison against `git show HEAD:content/ibo/<file>.csv`: join by `source_key` and assert all 157 target fields and English explanation fields are byte-for-byte equal. Assert 57 word, 50 phrase, 50 proverb, 157 English, and 157 Dutch-template rows.

### Task 3: Implement the fresh schema

**Files:**
- Modify: `db/schema.sql`

- [ ] **Step 1: Add language roles and remove explanation columns**

Add `is_learnable BOOLEAN NOT NULL DEFAULT FALSE` and `is_meta BOOLEAN NOT NULL DEFAULT FALSE` to `languages`. Remove the three explanation columns and `proverbs_need_meaning` check from `content_items`.

- [ ] **Step 2: Create translations after `app_users` is available**

Create `content_translations` with the requested columns and primary/foreign keys, plus its `touch_updated_at` trigger.

- [ ] **Step 3: Add the proverb trigger**

Define a `BEFORE INSERT OR UPDATE` trigger function which queries `content_items.content_type`; if it is `proverb` and `NEW.cultural_note IS NULL`, raise a descriptive exception, then return `NEW`.

- [ ] **Step 4: Scope flags and update dependent views**

Add nullable `meta_language_id`, replace the unique index with the `COALESCE(meta_language_id, 0)` expression, and join translations/meta-languages in `admin_flag_queue` so it exposes generic translation data.

- [ ] **Step 5: Recreate the test database and verify schema tests progress**

Drop/recreate the test database schema using the project test setup, then run the three new database tests. Expected: trigger and flag tests pass; count test still fails until the seed loader is updated.

### Task 4: Split seed loading into target content and translations

**Files:**
- Modify: `db/seed/seed.py`

- [ ] **Step 1: Update content validation**

Remove explanation requirements from `validate_rows`; retain source-key, content type, category, difficulty, target text, duplicate, and tone-policy checks.

- [ ] **Step 2: Add translation parsing and pre-write validation**

Load `content/meta_languages.yaml` and every `translations/*.csv`. Validate required headers, duplicate keys, keys belonging to the target content, and require each proverb's English row to have a non-empty translation and cultural note. Raise `SeedError` containing filename, row/source key, and the missing field.

- [ ] **Step 3: Upsert language roles**

Extend `upsert_language` to write `is_learnable` and `is_meta`. Upsert meta-language entries before target languages; mark the existing Igbo language as learnable without making it meta.

- [ ] **Step 4: Make content upserts language-neutral**

Remove explanation/example parameters from `upsert_content`, preserving all existing natural-key, toned-text, audio, and ordering behavior.

- [ ] **Step 5: Add translation upserts**

Resolve the meta-language by filename/code and content by source key. Skip blank `translation` rows. Insert/upsert `(content_id, meta_language_id)` and use `COALESCE(EXCLUDED.optional_column, content_translations.optional_column)` for optional fields so empty input never blanks populated data. Apply the same preservation to the required translation by skipping empty rows.

- [ ] **Step 6: Verify seed tests GREEN**

Run: `pytest -q backend/tests/test_api.py -k "translation_counts or proverb_cultural or flag_uniqueness"`

Expected: all three new database tests pass and report English 157, Dutch 0.

### Task 5: Join the configured translation in API and worklists

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/content.py`
- Modify: `backend/app/services/study.py`
- Modify: `db/seed/export_worklist.py`

- [ ] **Step 1: Add configuration and response fields**

Add `self.default_meta_language = os.getenv("DEFAULT_META_LANGUAGE", "eng")`. Rename `ContentItem.english_translation` to `translation` and add `meta_language: str`; do not add request parameters or fallback fields.

- [ ] **Step 2: Update content SQL**

Join `content_translations ct` and its `languages ml`, constrain `ml.code = %(meta_language)s`, select `ct.translation`, `ct.literal_translation`, `ct.cultural_note`, and `ml.code AS meta_language`, and search `ct.translation`. Supply the config value to list/count/detail queries.

- [ ] **Step 3: Update study SQL and shaping**

Join the configured meta-language in `_ITEMS_SQL`, select explanation fields from `ct`, rename internal row access to `translation`, and pass `meta_language` from settings through `build_session` parameters without exposing it in the route API.

- [ ] **Step 4: Update worklist SQL**

Read verify fields and explanation fields from `content_translations`; ensure flagged translation queries match `content_flags.meta_language_id` while item-level flags remain representable.

- [ ] **Step 5: Run API tests GREEN**

Run: `pytest -q backend/tests/test_api.py`

Expected: all tests pass with generic `translation` response fields and unchanged study answers.

### Task 6: Full verification and report capture

**Files:**
- Modify only files needed to correct failures found by verification.

- [ ] **Step 1: Run dry-run validation**

Run: `python db/seed/seed.py --all --dry-run`

Expected: successful validation of Igbo target content, English proverb notes, and both translation files, with no writes.

- [ ] **Step 2: Run formatting/lint checks**

Run: `ruff check backend db`

Expected: exit 0 with no diagnostics.

- [ ] **Step 3: Run the complete suite**

Run: `pytest -q`

Expected: 33 passed.

- [ ] **Step 4: Capture database evidence**

Query translation counts grouped by meta-language and extract the complete trigger function/trigger definition from the final schema for the handoff report.

- [ ] **Step 5: Verify the diff**

Run: `git diff --check` and inspect `git diff --stat` plus focused diffs for CSVs to confirm no target content changed and no forbidden scope was added.
