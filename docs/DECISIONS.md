# Decisions awaiting review

Tier B items: schema, auth, privacy, real data, paid services. Claude proposes; Michael decides.
Status: `open` until answered. Nothing here has been implemented.

## Review findings (2026-10-09, read-only review + live Supabase/Render checks)

| # | Severity | Finding | Proposed action | Tier |
|---|----------|---------|-----------------|------|
| F1 | High (fixed in this PR) | Seed runs on every boot (`RUN_SEED=true`) and overwrites `target_text` and `example_sentence` on `ON CONFLICT (source_key)`. Admin corrections to Igbo text are reverted on the next deploy. | Seed inserts only; never updates text on existing rows (or turn `RUN_SEED` off in prod). | B (touches real content) |
| F2 | High | `admin_flag_queue` view is SECURITY DEFINER (Supabase ERROR lint). | Recreate with `security_invoker = true`; verify backend role still reads it. | B (schema) |
| F3 | Medium | `rls_auto_enable()` is SECURITY DEFINER and executable by `anon`/`authenticated` via REST. | `REVOKE EXECUTE` from `anon, authenticated, public`. | B (schema) |
| F4 | Medium | Admin promotion trusts the `email` JWT claim; `email_verified` is not checked. Safe only while Supabase "Confirm email" stays on. | Require `email_verified` in `provision_user`. | B (auth) |
| F5 | Medium | No account deletion or data export endpoint. | See D1. | B (privacy) |
| F6 | Medium | Public profile (`/v1/profile/{slug}`) has no opt-out or slug rotation. | Default private, opt-in, revocable slug. See D1. | B (privacy) |
| F7 | Medium | Supabase free project paused after inactivity; app was down until restored. | Keep-alive ping (Tier A) and/or Pro. See D2. | A / B |
| F8 | Low | `/docs` and `/openapi.json` public in prod, exposing the admin API surface. | Disable in production or gate behind admin. | A |
| F9 | Low | No Sentry in code; no backend lockfile (`PyJWT>=`, `PyYAML>=` unpinned). | Instrument Sentry (DSN as env var); add a pinned lockfile. | A (DSN is B) |
| F10 | Low | Stale docstring in `main.py`; `ILIKE` search does not escape `%`/`_`; schema.sql RLS block is commented out but live DB has RLS on (drift). | Tidy; make schema.sql match live. | A |
| F11 | Info | CI is solid (schema idempotency, content validation, lint, frontend, API tests, image smoke test) and green on main. | None. | n/a |
| F12 | Info | Vercel connector returned 403 for team scope; frontend deployments not inspected. | Michael to re-authorize Vercel connector. | n/a |

Not verified: Supabase "Confirm email" setting, custom SMTP (a 429 magic-link rate limit was seen earlier), Render env values (CORS_ORIGINS).

## D1. Children's privacy and consent (consent age decided: 16)
Live DB currently has 0 child accounts, so this is best built before launch. Proposed build:
1. Age gate at onboarding; under the consent age, require parental consent (email-based) before account activation.
2. Account deletion + data export endpoints and Settings UI (FKs already cascade from `app_users`).
3. Public profile off by default; child accounts never public.
4. Privacy policy page; no analytics/Sentry PII for child accounts.
Decided 2026-10-09: consent age is 16 (Michael). Still open: whether the first release excludes under-16s instead of building the parental-consent flow, and legal confirmation of the Dutch rule.

## D2. Free-tier hosting (open)
- Supabase free pauses after ~7 days idle. Options: keep-alive ping (free, fragile) vs Pro (paid).
- Render free cold start 30-60 s. Options: accept for pilot vs paid instance.
Recommendation: keep-alive ping now; revisit before sending the link to 5-10 real users.

## D3. Sentry (open)
Create DSNs (frontend + backend) and add as env vars on Vercel/Render. Claude then adds instrumentation.

## D4. Carried over (open)
Alphabet rename to "Mkpụrụedemede — Alphabet"; tone marking (blocks the elephant word); 5 missing alphabet example words (f, l, sh, v, y); 50 blank Dutch proverbs.

## Resolved
- F1 seed overwrite (2026-10-09, approved by Michael): the seed no longer overwrites text on rows that are verified or were edited by an admin. Provenance: `verified_by` records who approved; `content_revisions.changed_by` records who entered an edit; every text change the seed itself makes is logged as a revision with no author (note starts with "seed:"), and skipped differences are printed as `KEPT` in the deploy log.
