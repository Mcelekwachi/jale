# Proposal: parental consent and child profiles

Status: **approved by Michael 2026-10-10 (Q1-Q7: yes to all; keep it simple, no extra knobs)**. Tier B (schema, auth, privacy).
Decided so far (Michael, 2026-10-09): consent age 16; under-16s are not excluded; a parent sets up the child; child profiles live under the parent; Resend as mail sender.

## What the user sees
1. **Age gate** (after first sign-in, before onboarding): "Are you 16 or older?" (asks birth year, stores only the outcome plus year for children).
   - 16+: continue as today.
   - Under 16 on their own: "Please ask a parent to set this up." Nothing is kept about them.
   - "I'm setting this up for my child": continue as the parent.
2. **Parent area** (Settings): add child (nickname, birth year), tick the consent statement (versioned text), see children, pause, export, delete.
3. **Profile switcher** in the header: parent / each child. Child mode hides Settings, account and sharing. Optional parent PIN to leave child mode (open question Q4).
4. The child never has an email, password or login. The parent's sign-in is the only credential.

## Design: a child profile is an `app_users` row
Every progress table (`user_progress`, `user_daily_activity`, `user_stats`, `study_answer_receipts`, `user_preferences`) is keyed by `user_id` referencing `app_users`, and about 100 query sites use it. Making a child profile its own `app_users` row (no email, no auth identity) means **none of those tables or queries change**. The parent's token plus an `X-Profile-Id` header selects the child; the backend checks the child belongs to the caller and consent is active. A separate `learner_profiles` table would give the same user experience but rekeys 6 tables and about 100 queries on a live database with 5 users; I do not recommend it.

### Schema (additive, idempotent, no data rewritten)
- `app_users.parent_user_id UUID NULL REFERENCES app_users(id) ON DELETE CASCADE` (NULL = adult). Deleting the parent erases the children.
- `app_users.birth_year SMALLINT NULL` (children only; year, not date).
- `app_users.age_confirmed_at TIMESTAMPTZ NULL` (NULL = must pass the age gate; existing 5 users are gated at next sign-in).
- New `parental_consents(id, parent_user_id, child_user_id, policy_version, granted_at)`: the evidence record while the child exists. No IP, no free text. Withdrawal = deleting the child, which erases the row too.
- Child rows: `email NULL`, `share_slug NULL`, `role = learner` (CHECK: a child can never be admin/contributor).
- New tables get RLS enabled explicitly in `schema.sql` (matching the live database).

### API (all under the parent's token)
- `GET/POST /v1/me/children`, `DELETE /v1/me/children/{id}` (deleting withdraws consent and erases the child's data). No pause endpoint: keep it simple.
- `GET /v1/me/children/{id}/export` and `GET /v1/me/export` (JSON)
- `DELETE /v1/me` (account deletion; children cascade) - also closes review finding F5
- `POST /v1/me/age` (age gate answer)
- `X-Profile-Id` handled in `current_user`; ignored by all `/v1/admin/*` routes.
- Child profiles are excluded from the public profile endpoint and from flags/contributor features.

### Privacy rules enforced in code
No email, photo, public slug or reminders by email for children. Sentry/analytics get no user context for child profiles. Only nickname, birth year and progress are stored. Parent can export or delete at any time; withdrawal of consent deletes the child's data after confirmation.

### Consent evidence
The parent is signed in with a verified email (magic link or Google), ticks a versioned consent statement, and the grant is stored in `parental_consents`. A receipt email with a withdrawal link is sent via Resend (needs a verified sending domain; the sender is pluggable so the flow works without it, logging the link in development).

## Build order (each a PR, CI green before merge)
1. Schema + backend: children CRUD, `X-Profile-Id`, export, delete, age endpoint, tests (including "child can never reach admin or public profile").
2. Frontend: age gate, parent area, profile switcher, child mode.
3. Privacy policy page and consent copy (draft for lawyer review).
4. Resend receipt emails (blocked on a sending domain).

## Open questions for Michael
- Q1 Approve "child = `app_users` row" instead of a separate profiles table?
- Q2 Deleting an account should also delete the Supabase login. That needs a `SUPABASE_SERVICE_ROLE_KEY` on Render (a powerful secret, set by you). Otherwise the login remains and the person can re-register.
- Q3 Nickname only for children (we recommend discouraging real names)?
- Q4 Parent PIN to leave child mode: include in v1?
- Q5 Existing 5 users get the age gate on next sign-in: OK?
- Q6 16-17-year-olds sign up on their own without parental consent (research says no statutory requirement; one source disagrees): OK pending lawyer check?
- Q7 Privacy policy and consent wording: I draft, a lawyer reviews before launch with real children.

## Decisions (Michael, 2026-10-10)
Q1-Q7 all approved. Constraint: do not over-parametrize. Consequences: one optional env var (`SUPABASE_SERVICE_ROLE_KEY`, set by Michael on Render, used only to delete the login on account deletion); the parent PIN is a simple hashed PIN, a soft lock on the device (no lockout logic); no pause endpoint; one consent policy version constant in code.
