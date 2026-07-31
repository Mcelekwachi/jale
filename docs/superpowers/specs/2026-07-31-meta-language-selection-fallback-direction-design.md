# Meta-Language Selection, Fallback, and Study Direction Design

## Objective

Allow clients to request an explanation language, transparently fall back per content row to the configured default, support both study directions, and report published translation coverage. This extends the existing `content_translations` structure without duplicating content or adding target languages.

## Request Validation

`/v1/content`, `/v1/content/{id}`, and `/v1/tracks/{slug}/units/{position}/items` gain an optional `meta_language` ISO 639-3 query parameter. Omission uses `DEFAULT_META_LANGUAGE`. A shared database helper resolves the code and requires `languages.is_meta = TRUE`; an unknown or non-meta code returns HTTP 400.

The study endpoint also gains a `direction` query parameter represented by a closed enum: `target_to_meta` is the default and `meta_to_target` is the alternative. No content rows are duplicated to represent direction.

## Translation Resolution

Content and study queries join `content_translations` twice: one `LEFT JOIN` for the requested meta-language and one for the configured default. The default translation row is required for a content item to be returned; the requested row is optional.

Resolution happens independently for every content row. `meta_language` in each response is the requested code. `meta_language_used` is computed per row as:

```sql
CASE
  WHEN requested_translation.content_id IS NOT NULL THEN requested_meta.code
  ELSE default_meta.code
END
```

If no requested row exists, all served translation fields come from the default row. If a requested row exists, its required `translation` is served, while `literal_translation` and `cultural_note` independently use `COALESCE(requested_value, default_value)`. This ensures a partially authored proverb translation still carries the default-language lesson.

Content search applies to `target_text` and the same resolved translation expression used in the response. It therefore searches requested-language text when a requested row exists and default-language text only for rows that fall back.

## Study Direction and Quiz Options

For `target_to_meta`, the target text is the prompt and the resolved translation is the answer. For `meta_to_target`, the resolved translation is the prompt and the target text is the answer.

Quiz options always use the answer side. Target answers use target-language distractors. Meta-language answers use translation distractors from the same actual language as the correct answer. One pooled distractor query returns both requested and default translations; shaping chooses requested-language distractors for rows whose `meta_language_used` is requested and default-language distractors for fallback rows. Null or duplicate distractors are removed before sampling.

## Meta-Language Coverage Endpoint

`GET /v1/languages/meta` lists available active meta-languages. Each response contains language identity fields plus:

- `translated_count`: published target content items that have a non-empty translation row in that meta-language.
- `total_count`: published target content items in scope.

Both numerator and denominator count only `content_items.status = 'published'`. Counts are returned separately; the API does not calculate a percentage.

## Response Models

Every content or study item carrying translated content includes both:

- `meta_language`: requested meta-language code.
- `meta_language_used`: actual per-row language code selected by fallback.

The existing translation, gloss, cultural-note, prompt, answer, audio, verification, and flag fields retain their roles.

## Tests

Tests are written before implementation and cover:

- unknown and non-meta codes returning 400 on all three endpoint families;
- Dutch requests falling back to English when no Dutch row exists;
- insertion of exactly one Dutch translation followed by a mixed response where that item reports `meta_language_used = "nld"` and other items report `"eng"`;
- a requested row with null literal translation or cultural note inheriting each missing optional field from English;
- content search matching a requested Dutch translation such as `hallo`;
- `meta_to_target` swapping prompt and answer relative to `target_to_meta`;
- quiz options matching the actual answer side and, for translated answers, the per-item language actually used;
- published-only `translated_count` and `total_count` from `/v1/languages/meta`.

## Non-Goals and Safety

No persona enum changes, second target language, Igbo text/source-key edits, content duplication, fallback HTTP round trip, or translation-row duplication will be introduced. The unrelated pending `.github/workflows/release.yml` edit remains untouched by this feature.
