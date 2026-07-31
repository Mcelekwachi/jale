# Meta-Language Selection, Fallback, and Study Direction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add validated meta-language selection, per-row SQL fallback, bidirectional study sessions, language-matched quiz options, and published translation coverage.

**Architecture:** A shared validator resolves requested ISO 639-3 meta-language codes. Content and study queries use requested/default translation joins and per-row expressions; study shaping applies direction without duplicating content. The existing languages router exposes coverage aggregates.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, psycopg 3, PostgreSQL 15+, pytest, Ruff.

---

## File Map

- Create `backend/app/services/meta_languages.py`: shared meta-language validation.
- Modify `backend/app/schemas.py`: direction enum, provenance fields, coverage model.
- Modify `backend/app/routers/content.py`: query parameter, validation, per-row fallback/search SQL.
- Modify `backend/app/routers/tracks.py`: meta-language and direction query parameters.
- Modify `backend/app/routers/languages.py`: published translation coverage endpoint.
- Modify `backend/app/services/study.py`: fallback SQL, direction shaping, language-matched distractors.
- Modify `backend/tests/test_api.py`: failing API, fallback, coverage, and direction tests.
- Preserve `.github/workflows/release.yml` exactly as currently modified and do not touch persona/content data.

### Task 1: Write failing behavior tests

**Files:**
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Add invalid meta-language tests**

Parametrize `/v1/content`, a known `/v1/content/{id}`, and a known study-session URL with `meta_language=zzz` and `meta_language=ibo`. Assert HTTP 400 for both unknown and non-meta codes.

- [ ] **Step 2: Add Dutch wholesale and mixed-row fallback tests**

First request `meta_language=nld` against the empty Dutch seed and assert all returned rows have `meta_language == "nld"`, `meta_language_used == "eng"`, and non-empty translations. Then use a rollback-isolated psycopg transaction to insert exactly one Dutch translation for a selected content item, request a page containing it, and assert that row uses `nld` while every other row uses `eng`.

- [ ] **Step 3: Add optional-field and resolved-search tests**

Insert a Dutch row for one proverb with `translation="Nederlands spreekwoord"` and null optional fields. Assert its translation is Dutch while literal/cultural fields equal the English row. Insert `translation="hallo"` for a Ndewo item and assert `/v1/content?q=hallo&meta_language=nld` returns it.

- [ ] **Step 4: Add direction and quiz-language tests**

Request the same deterministic session in both directions and assert prompt/answer swap. For quiz sessions, assert each correct option equals `answer`; `target_to_meta` translated answers and distractors come from that item's `meta_language_used`, while `meta_to_target` answers/options are target text. Use inserted Dutch translations where necessary to distinguish Dutch from English.

- [ ] **Step 5: Add coverage tests**

Assert `/v1/languages/meta` returns English `translated_count=157`, Dutch `translated_count=0`, and `total_count=157`. Within a rollback-isolated transaction, add one Dutch translation and a draft content item/translation, then assert Dutch numerator rises only by one and denominator remains 157.

- [ ] **Step 6: Verify RED**

Run from `backend`: `..\.venv\Scripts\pytest.exe -q tests/test_api.py`

Expected with a database: new tests fail because parameters, fallback provenance, direction, and coverage endpoint do not exist. Without `DATABASE_URL`, record skips without claiming RED.

- [ ] **Step 7: Commit only tests**

Commit `backend/tests/test_api.py` with message `test: cover meta-language fallback and study direction`.

### Task 2: Add shared validation, response models, content fallback, and coverage

**Files:**
- Create: `backend/app/services/meta_languages.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/content.py`
- Modify: `backend/app/routers/languages.py`

- [ ] **Step 1: Implement the validator**

Create an async helper that selects `code` from `languages WHERE code = %(code)s AND is_meta`, using the requested code or `get_settings().default_meta_language`. Raise `HTTPException(status_code=400, detail=...)` when no row matches and return the validated code otherwise.

- [ ] **Step 2: Extend response models**

Add `StudyDirection` with `target_to_meta` and `meta_to_target`. Add `meta_language_used: str` to `ContentItem` and `StudyItem`. Add `MetaLanguageCoverage` containing language identity, `is_active`, `translated_count`, and `total_count`.

- [ ] **Step 3: Implement content dual joins and expressions**

Validate the parameter in both content handlers. Join requested/default language IDs, `LEFT JOIN` requested translations, and join the default translation row. Select:

```sql
COALESCE(rt.translation, dt.translation) AS translation,
COALESCE(rt.literal_translation, dt.literal_translation) AS literal_translation,
COALESCE(rt.cultural_note, dt.cultural_note) AS cultural_note,
%(meta_language)s::text AS meta_language,
CASE WHEN rt.content_id IS NOT NULL THEN %(meta_language)s::text
     ELSE %(default_meta_language)s::text END AS meta_language_used
```

Use `COALESCE(rt.translation, dt.translation)` in search and identical joins in count/detail queries. Pass requested and default codes separately; do not fetch twice.

- [ ] **Step 4: Implement published-only coverage**

Register `/meta` before `/{code}/categories`. Return active `is_meta` languages and aggregate published content with `count(*) FILTER (WHERE ct.content_id IS NOT NULL)` as `translated_count` and a published-content denominator as `total_count`. Keep numerator and denominator in one SQL query and prevent translation joins from multiplying totals.

- [ ] **Step 5: Verify focused tests GREEN**

Run content-validation/fallback/search/coverage tests. Expected: pass with PostgreSQL; accurately report skips otherwise. Run Ruff and formatting checks on changed files.

- [ ] **Step 6: Commit**

Commit the four scoped implementation files with message `feat: resolve requested meta-language translations`.

### Task 3: Implement study direction and language-matched quiz distractors

**Files:**
- Modify: `backend/app/routers/tracks.py`
- Modify: `backend/app/services/study.py`

- [ ] **Step 1: Validate study request parameters**

Accept `meta_language: str | None` and `direction: StudyDirection = target_to_meta` on the session endpoint. Resolve the meta-language with the shared helper, then pass the validated code, configured default code, and direction into `build_session`.

- [ ] **Step 2: Apply per-row fallback in item SQL**

Replace the single translation join with requested/default joins and the same translation, optional-field, `meta_language`, and per-row `meta_language_used` expressions used by content queries.

- [ ] **Step 3: Shape prompt and answer by direction**

For `target_to_meta`, set `prompt=target_text`, `answer=translation`. For `meta_to_target`, reverse them. Apply this uniformly to flashcard, phrase, proverb, and quiz modes.

- [ ] **Step 4: Fetch both distractor sides once**

The pooled distractor query selects target text, requested translation, and default translation. For target answers choose target text. For meta answers whose item used requested language choose only non-null requested translations; for fallback items choose default translations. Remove the correct answer and duplicates before sampling three options.

- [ ] **Step 5: Verify focused study tests GREEN**

Run direction, quiz, fallback, and invalid-code tests. Then run Ruff and formatting checks on both changed files.

- [ ] **Step 6: Commit**

Commit with message `feat: add bidirectional study sessions`.

### Task 4: Full verification and protected-data audit

**Files:**
- Modify only feature files if verification reveals a defect.

- [ ] **Step 1: Run the requested checks**

Run `python db/seed/seed.py --all --dry-run`, `ruff check backend db`, `ruff format --check backend db`, and from `backend`, `pytest -q`. Record exact outputs and distinguish passes from environment skips.

- [ ] **Step 2: Audit SQL/runtime behavior**

With PostgreSQL, confirm mixed Dutch/English provenance, published-only coverage, invalid meta-language 400 responses, field-level optional fallback, both directions, and quiz option language. If PostgreSQL remains unavailable, use repository CI or report the precise blocker without claiming runtime success.

- [ ] **Step 3: Audit protected scope**

Compare content CSV hashes/parsed protected fields to the feature base; assert no persona enum, target-language, Igbo text, or source-key changes. Confirm `.github/workflows/release.yml` remains only the user's pre-existing pending edit and is absent from feature commits.

- [ ] **Step 4: Final review**

Run `git diff --check`, inspect the full feature diff, and request whole-implementation spec and quality review before reporting completion.
