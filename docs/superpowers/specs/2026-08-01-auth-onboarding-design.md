# Supabase Authentication and Onboarding Write Path Design

## Objective

Add local Supabase JWT verification, lazy user provisioning, authenticated profile/preferences/onboarding endpoints, and stored-preference track resolution. Existing public read endpoints remain unchanged. Progress, streak, answer, flag, and admin features remain out of scope.

## Configuration and Dependencies

`Settings` gains `SUPABASE_JWT_SECRET` and `SUPABASE_PROJECT_URL` with no defaults and `SUPABASE_JWT_AUDIENCE` defaulting to `authenticated`. The variables are documented in `.env.example`; Render receives the URL and audience values plus a dashboard-only `sync: false` secret. Render also declares the existing pool settings with minimum 1 and maximum 5.

PyJWT is pinned below its next major version in `backend/requirements.txt`. No other dependency is added.

## Authentication Boundary

`backend/app/auth.py` verifies bearer tokens locally with HS256, the configured secret, expiry validation, and audience validation. It never calls Supabase, logs tokens, or exposes which verification check failed. Missing or invalid credentials produce the same generic HTTP 401 response.

The verified identity contains the UUID `sub`, email, display name, and avatar URL. Display-name claim precedence is `user_metadata.full_name`, `user_metadata.name`, top-level `name`, then the email local-part. Avatar precedence is `user_metadata.avatar_url`, then top-level `avatar_url`.

Three dependencies are exposed:

- `current_user`: requires valid authentication and returns the provisioned user.
- `optional_current_user`: returns `None` when the Authorization header is absent, but returns 401 for a malformed or invalid supplied token.
- `require_admin`: requires `current_user` and returns 403 unless the provisioned database role is `admin`.

## Lazy Provisioning

Provisioning runs inside one database transaction on every valid identity, using conflict-safe inserts so concurrent first requests converge on one row:

1. Insert `app_users` with UUID, claims, learner role, and a URL-safe share slug.
2. Generate the slug from the display name or email local-part plus a short random suffix. Retry when another user owns the slug; if a concurrent request already created the same user, use that row.
3. Insert one `user_stats` row with `ON CONFLICT DO NOTHING`.
4. Insert one `user_preferences` row with `onboarding_status = 'not_started'` and `active_language_id` resolved from `DEFAULT_LANGUAGE`.

`meta_language_id` remains null at provisioning. Null means the user has not made an explicit explanation-language choice, allowing future locale detection to choose a language before API fallback.

Each authenticated request conditionally updates `last_seen_at` only when it is null or older than one hour.

## Schema

The fresh-install schema adds this nullable preference column:

```sql
meta_language_id SMALLINT NULL REFERENCES languages(id)
```

No migration framework or RLS is added. `ARCHITECTURE.md` records RLS as deferred because the service-role API is currently the only database client; enabling RLS now would be bypassed and create false assurance.

## Authenticated Endpoints

All endpoints use `/v1/me`, obtain the user ID only from the verified token, and filter every query by that ID.

### `GET /v1/me`

Returns profile fields including `share_slug`, plus all preference values and onboarding state.

### `PATCH /v1/me/preferences`

Uses a strict partial Pydantic model with unknown fields forbidden. Only fields explicitly present in the request are updated; omitted values remain unchanged. The endpoint never changes `onboarding_status`.

Allowed fields are `active_language_id`, `meta_language_id`, `age_band`, `connection`, `goal`, `style`, `daily_minutes`, `reminder_enabled`, `reminder_time`, `timezone`, `placement_level`, and `onboarding_last_screen`.

Null rules:

- `active_language_id`, `age_band`, `connection`, `goal`, and `style` reject explicit null with 422.
- `meta_language_id`, `reminder_time`, `placement_level`, and `onboarding_last_screen` accept explicit null to clear a prior value.
- Other field nullability follows their existing database constraints and request types.

`meta_language_id` is validated through the existing meta-language validation service; an ID that does not identify `is_meta = TRUE` returns 422. Enum values are validated by Pydantic.

### `POST /v1/me/onboarding/complete`

Takes no body. It changes `not_started` to `completed` and records `completed_at`. When already `completed` or `skipped`, it returns 200 without changing either terminal status or timestamp.

### `POST /v1/me/onboarding/skip`

Accepts no body, `{}`, or `{ "onboarding_last_screen": value }`, where the value is null or an integer from 1 through 8. An omitted field preserves the stored screen; explicit null clears it. It changes `not_started` to `skipped`. When already `completed` or `skipped`, it returns 200 without changing terminal state or screen.

### `GET /v1/me/track`

Reads the authenticated user's stored active language and persona preferences, calls the existing `track_resolver.resolve`, and shapes the same resolved-track structure as the public endpoint. Empty persona preferences fall through to the data-defined default rule. No resolver logic is duplicated.

## Service Boundaries

- `auth.py`: bearer parsing, JWT verification, auth dependencies.
- `services/users.py`: transactional provisioning, profile/preferences persistence, onboarding transitions.
- `routers/me.py`: thin HTTP validation and service orchestration.
- `services/track_resolver.py`: unchanged single source of curriculum resolution logic.

Raw psycopg SQL remains the persistence pattern; no ORM or middleware-wide authentication pattern is introduced.

## Testing

Tests mint HS256 JWTs with a local test secret and require no Supabase network access. They cover:

- absent, malformed, expired, and wrong-audience tokens returning 401;
- optional auth returning null only for a missing header and rejecting invalid supplied tokens;
- first-request provisioning of exactly one user, preferences row, and stats row;
- new preferences having `meta_language_id IS NULL`;
- repeat and concurrent-safe provisioning behavior;
- unique share slugs for equal display names;
- partial PATCH preserving omitted fields and onboarding status;
- 422 for unknown fields, invalid enums, null persona values, null active language, and non-meta language IDs;
- allowed explicit-null clearing behavior;
- completion idempotency and stable `completed_at`;
- skip at screen 4, skip without a body preserving an existing screen, and terminal-state idempotency;
- default and native stored-preference track resolution;
- user isolation, with no client-supplied user ID path or body field;
- `require_admin` behavior without adding admin endpoints;
- unchanged behavior and response shapes for existing public endpoints.

## Non-Goals and Architecture Locks

No password storage, Supabase API calls, RLS, frontend work, progress/streak/answer/flag writes, admin endpoints, persona enum changes, second target language, Igbo or translation content edits, language-specific schema names, or Phase 2 work are included.
