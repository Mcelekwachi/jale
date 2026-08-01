# Supabase Authentication and Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local Supabase JWT authentication, conflict-safe lazy provisioning, authenticated profile/preferences/onboarding writes, and stored-preference track resolution.

**Architecture:** `auth.py` owns bearer/JWT verification and FastAPI dependencies; `services/users.py` owns user-scoped SQL and provisioning transactions; `routers/me.py` remains a thin HTTP layer and delegates curriculum selection to the existing `track_resolver`. The fresh schema gains only the nullable explicit meta-language preference.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, psycopg 3, PostgreSQL 16, PyJWT 2.x, pytest.

---

## File Map

- Modify `backend/requirements.txt`: pin PyJWT below version 3.
- Modify `backend/app/config.py`, `.env.example`, `render.yaml`: Supabase JWT settings and Render pool settings.
- Modify `db/schema.sql`: nullable `user_preferences.meta_language_id`.
- Create `backend/app/auth.py`: token verification and auth dependencies.
- Create `backend/app/services/users.py`: provisioning and user-owned persistence.
- Create `backend/app/routers/me.py`: authenticated `/v1/me` endpoints.
- Modify `backend/app/services/meta_languages.py`: reusable ID-based meta-language validation.
- Modify `backend/app/schemas.py`: strict request and response models.
- Modify `backend/app/main.py`: register the new router only.
- Modify `backend/tests/conftest.py`: deterministic test JWT configuration/fixtures.
- Create `backend/tests/test_auth_onboarding.py`: authentication/onboarding integration tests.
- Modify `ARCHITECTURE.md`: explain why RLS is deferred.

### Task 1: Add failing authentication and provisioning tests

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth_onboarding.py`

- [ ] **Step 1: Add local JWT fixtures**

Set `SUPABASE_JWT_SECRET=test-supabase-secret`, `SUPABASE_JWT_AUDIENCE=authenticated`, and a test project URL before app creation. Add a `mint_token` fixture using HS256 with `sub`, `aud`, `exp`, `email`, and optional `user_metadata` claims. Generate unique UUID subjects per test and provide an Authorization-header helper.

- [ ] **Step 2: Test authentication failures**

Assert `/v1/me` returns the same generic 401 detail for no token, malformed bearer token, expired token, and a correctly signed wrong-audience token. Add a direct dependency/unit test showing optional auth returns `None` only when the header is absent and rejects an invalid supplied token.

- [ ] **Step 3: Test lazy provisioning**

On the first valid `/v1/me` request, assert one matching row exists in each of `app_users`, `user_preferences`, and `user_stats`; preferences have the default active language and `meta_language_id IS NULL`. Repeat the request and assert counts remain one. Provision two UUIDs with the same display name and assert distinct URL-safe `share_slug` values.

- [ ] **Step 4: Test last-seen throttling and admin dependency**

Backdate `last_seen_at`, make a request, and assert it advances; make a second immediate request and assert it remains unchanged. Exercise `require_admin` directly or through a test-only dependency override: learner yields 403, a database-updated admin is accepted. Do not add an admin route.

- [ ] **Step 5: Verify RED**

Run from `backend`: `pytest -q tests/test_auth_onboarding.py`. Expected with PostgreSQL: import/route failures because auth and `/v1/me` do not exist. If no database is available, report skips without claiming RED.

- [ ] **Step 6: Commit tests**

Commit only test fixtures/tests as `test: cover authentication and provisioning`.

### Task 2: Implement configuration, schema, JWT verification, and provisioning

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Modify: `.env.example`
- Modify: `render.yaml`
- Modify: `db/schema.sql`
- Create: `backend/app/auth.py`
- Create: `backend/app/services/users.py`
- Modify: `backend/app/services/meta_languages.py`

- [ ] **Step 1: Pin and install PyJWT**

Add `PyJWT>=2.10,<3` because JWT signature/expiry/audience verification must happen locally without Supabase network calls. Install from the updated requirements into the worktree environment without creating or committing `uv.lock`.

- [ ] **Step 2: Add configuration and schema fields**

Read the three Supabase environment variables in `Settings`. Mirror them in `.env.example`; add them to Render with `SUPABASE_JWT_SECRET` as `sync: false`, and add Render `DB_POOL_MIN=1`/`DB_POOL_MAX=5`. Add nullable `meta_language_id SMALLINT REFERENCES languages(id)` to `user_preferences`; provisioning must not set it.

- [ ] **Step 3: Implement local token verification**

Parse `Authorization: Bearer <token>`, decode with `jwt.decode(..., algorithms=["HS256"], audience=settings.supabase_jwt_audience)`, require a UUID `sub`, and normalize claims. Catch all JWT/claim failures and raise one generic 401 with `WWW-Authenticate: Bearer`; never log token material.

- [ ] **Step 4: Implement conflict-safe provisioning**

Inside one pooled connection transaction, resolve the default language, generate a slug base with Unicode normalization and URL-safe characters, then attempt:

```sql
INSERT INTO app_users (id, email, display_name, avatar_url, role, share_slug)
VALUES (%(id)s, %(email)s, %(display_name)s, %(avatar_url)s, 'learner', %(share_slug)s)
ON CONFLICT DO NOTHING
RETURNING id
```

If no row returns, query by user ID; retry a new suffix only when the user still does not exist. Insert stats and preferences with `ON CONFLICT (user_id) DO NOTHING`; preferences set `active_language_id` but omit `meta_language_id`. Conditionally update `last_seen_at` using `last_seen_at IS NULL OR last_seen_at < now() - interval '1 hour'`.

- [ ] **Step 5: Expose dependencies**

`optional_current_user` returns `None` for no header or the provisioned row for a valid token. `current_user` converts `None` to generic 401. `require_admin` checks `role` and returns 403 for non-admin users.

- [ ] **Step 6: Reuse meta-language validation by ID**

Add an ID validator to `services/meta_languages.py` querying `languages.id` with `is_meta`. It raises 422 for a non-meta or unknown ID and is reused by the preferences service/router rather than duplicating SQL.

- [ ] **Step 7: Verify authentication tests GREEN**

Run focused auth/provisioning tests, Ruff lint/format, and `git diff --check`. Commit as `feat: add Supabase JWT authentication`.

### Task 3: Add failing preference and onboarding endpoint tests

**Files:**
- Modify: `backend/tests/test_auth_onboarding.py`

- [ ] **Step 1: Test GET and partial PATCH ownership**

Assert GET returns profile/share slug plus nested preferences. PATCH one field and verify all omitted fields and `onboarding_status` remain unchanged. Unknown fields and invalid enums return 422. Use two tokens and assert each `/v1/me` response always reflects its own UUID; there is no client user-ID parameter.

- [ ] **Step 2: Test null and meta-language rules**

Parametrize explicit null for `active_language_id`, `age_band`, `connection`, `goal`, and `style` and expect 422. Assert null clears `meta_language_id`, `reminder_time`, `placement_level`, and `onboarding_last_screen`. PATCH a non-meta language ID and expect 422; patch a valid meta ID and expect success.

- [ ] **Step 3: Test terminal onboarding behavior**

Complete twice and assert both responses are 200 and `completed_at` is unchanged. Skip at screen 4 and assert stored screen/status. Establish a prior screen, then skip with no body and assert status becomes skipped without overwriting the screen. Assert completed/skipped terminal states cannot overwrite one another.

- [ ] **Step 4: Verify RED and commit**

Run focused tests; expect missing route/model/service failures with PostgreSQL. Commit tests only as `test: cover profile preferences and onboarding writes`.

### Task 4: Implement profile, preferences, and onboarding endpoints

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/users.py`
- Create: `backend/app/routers/me.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Define strict models**

Add profile/preferences responses and a `PreferencePatch` with `ConfigDict(extra="forbid")`. Use a model validator that checks `model_fields_set` and rejects explicit null for active language/persona fields. Define clearable nullable fields and `OnboardingSkipRequest(onboarding_last_screen: int | None = Field(default=None, ge=1, le=8))`.

- [ ] **Step 2: Implement user-scoped profile SQL**

Fetch app user plus preferences using `WHERE u.id = %(user_id)s`; return a nested response. No query accepts a client-provided user ID.

- [ ] **Step 3: Implement partial preference updates**

Build `SET` clauses only from a fixed field-to-column map and `payload.model_fields_set`, allowing explicit null only where modeled. Validate `meta_language_id` by the shared helper. Execute `UPDATE user_preferences ... WHERE user_id = %(user_id)s RETURNING ...`; never include onboarding status in the map.

- [ ] **Step 4: Implement terminal transitions**

Complete updates only `WHERE user_id = ... AND onboarding_status = 'not_started'`, setting status and `completed_at=now()`. Skip uses the same terminal guard and changes the screen only when the body field was supplied; no body/empty object preserves it, explicit null clears it. Return the current profile after either operation.

- [ ] **Step 5: Register thin authenticated routes**

Add GET profile, PATCH preferences, POST complete, and POST skip under `/v1/me`, each taking `current_user` via `Depends`. Register only this router in `main.py`; existing routers remain unchanged.

- [ ] **Step 6: Verify tests GREEN and commit**

Run focused endpoint tests plus all existing public tests; lint/format/diff-check. Commit as `feat: add authenticated onboarding endpoints`.

### Task 5: Add stored-preference track resolution

**Files:**
- Modify: `backend/tests/test_auth_onboarding.py`
- Modify: `backend/app/services/users.py`
- Modify: `backend/app/routers/me.py`

- [ ] **Step 1: Write failing track tests**

Assert a newly provisioned user resolves the default `ibo_foundations` track. PATCH `connection=aboriginal_native` and assert `/v1/me/track` resolves `ibo_native_advanced`, matching the public resolver. Ensure the response includes units and resolver metadata.

- [ ] **Step 2: Implement by delegation**

Fetch the user's stored active-language code and persona fields with a user-ID filter. Call `track_resolver.resolve` with those values, then `track_resolver.get_units`; shape `ResolvedTrack` exactly like the public endpoint. Do not copy `_RESOLVE_SQL` or add persona branches.

- [ ] **Step 3: Verify and commit**

Run focused and complete tests, Ruff checks, and diff-check. Commit as `feat: resolve authenticated user track`.

### Task 6: Document authorization boundary and verify the branch

**Files:**
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Document deferred RLS**

State that all `/v1/me` SQL scopes by the token-derived user UUID. Explain RLS is intentionally deferred while the service-role API is the sole database client because it would be bypassed and imply protection it does not provide.

- [ ] **Step 2: Run required verification**

Run `pytest -q`, `ruff check backend db`, `ruff format --check backend db`, and `python db/seed/seed.py --all --dry-run`. Record exact results; do not count skips as passes.

- [ ] **Step 3: Audit locks and hygiene**

Confirm no persona enum, content, translation, public endpoint shape, RLS statement, migration framework, second target language, forbidden artifact, or unrelated write feature changed. Confirm PyJWT is the only dependency addition and report why.

- [ ] **Step 4: Final review**

Run `git diff --check`, inspect all branch commits against `11abe28`, and obtain final spec/quality review before pushing or opening a PR.
