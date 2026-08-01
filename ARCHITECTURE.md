# Jalɛ — Phase 1 Architecture

Central Igbo PoC. Everything below exists to make one promise true:
**adding Yoruba is a content job, not an engineering job.**

---

## 1. Repository structure

```
jale/
├── README.md
├── docker-compose.yml              # postgres + backend for local dev
│
├── content/                        # ← the "add a language" surface
│   └── ibo/
│       ├── language.yaml           # name, endonym, dialects, categories
│       ├── words.csv               # 57 rows
│       ├── phrases.csv             # 50 rows
│       ├── proverbs.csv            # 50 rows
│       └── tracks.yaml             # persona → curriculum mapping
│   (Phase 2: content/yor/ … same five files, zero code)
│
├── db/
│   ├── schema.sql                  # canonical DDL (this delivery)
│   ├── migrations/                 # alembic versions
│   └── seed/
│       ├── seed.py                 # reads content/*/ → upserts by source_key
│       └── placeholder_audio.py    # generates TTS stubs for every item
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── deps.py                 # auth, current_user, require_admin
│   │   ├── models/                 # SQLAlchemy — mirrors schema.sql 1:1
│   │   ├── schemas/                # pydantic request/response
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── onboarding.py       # GET/PUT preferences, resolve track
│   │   │   ├── content.py          # browse/search, per-mode item feeds
│   │   │   ├── study.py            # submit answer, SRS update, xp
│   │   │   ├── progress.py         # streak, stats, share profile
│   │   │   ├── flags.py
│   │   │   └── admin.py            # flag queue, edit, verify, permissions
│   │   └── services/
│   │       ├── track_resolver.py   # preferences → track (data-driven)
│   │       ├── srs.py              # Leitner box → due_at
│   │       ├── streaks.py          # timezone-correct day rollover
│   │       └── audio.py            # storage URLs
│   └── tests/
│
├── frontend/
│   ├── public/                     # manifest.json, icons, service worker
│   └── src/
│       ├── main.tsx
│       ├── api/                    # typed client, one file per router
│       ├── routes/
│       │   ├── onboarding/         # Screen1..Screen8, skippable stepper
│       │   ├── home/               # today's units, streak header
│       │   ├── study/              # Flashcard | Quiz | Phrase | Proverb
│       │   ├── settings/           # re-edit every onboarding answer
│       │   ├── profile/            # /u/:slug shareable
│       │   └── admin/
│       ├── components/
│       │   ├── AudioButton.tsx     # every content item, everywhere
│       │   ├── FlagButton.tsx      # every content item, everywhere
│       │   └── ContentCard.tsx
│       ├── store/                  # preferences + offline queue
│       └── i18n/                   # UI strings; app chrome ≠ lesson content
│
└── docs/
    ├── ARCHITECTURE.md             # this file
    └── CONTENT_GUIDE.md            # how a contributor adds/corrects a row
```

**Why `content/` is a first-class folder:** the 157 Phase 1 items live in
version-controlled CSV, not in a Python file of INSERT statements. A native
speaker you recruit in Arochukwu can be sent a CSV, edit it in Excel, and you
re-run `seed.py`. Upserts key on `source_key`, so re-seeding is idempotent and
never clobbers user progress.

---

## 2. Four schema decisions worth your review

**a) `target_text`, not `igbo_text`.** This is the one place your brief and the
extensibility goal conflict. A column named `igbo_text` means every query,
model, serializer and React prop carries the word "igbo" — and adding Yoruba
becomes a rename across the codebase. `target_text` + `language_id` keeps the
promise. The UI still says "Igbo" because it reads `languages.name`.

**b) Proverbs get three fields, not two.** `target_text` lives on
`content_items`; `translation` and `cultural_note` live on the corresponding
`content_translations` row for each meta-language. A database trigger prevents
a proverb translation from being saved without its cultural lesson.
`literal_translation` is optional and is where "Egbe bere ugo bere" becomes
"let the kite perch, let the eagle perch" before you explain what it *means*.
That literal layer is what native speakers judge you on.

**c) Persona → curriculum is data (`tracks` / `track_rules` / `track_units`),
not code.** Your five curriculum logic rules become five tracks and five rule
rows. `track_resolver.py` is ~30 lines and never changes again. The aboriginal
native speaker track simply has `min_difficulty = 'advanced'` and starts at
proverbs — "skip beginner content entirely" is a data value, not a branch.

**d) Units are queries, not lists.** A `track_unit` says "10 beginner words
from category *greetings*", not "content ids 1,4,7…". When you add 40 more
greetings next year, every existing learner's track absorbs them.

---

## 3. Phase 1 seed inventory

| Content type | Rows | Difficulty spread | Categories |
|---|---|---|---|
| word | 57 | beginner (numbers, body, family, everyday) | 8 |
| phrase | 50 | beginner → intermediate | 6 |
| proverb | 50 | advanced / native | wisdom, character, work, family, speech |

Categories proposed for Igbo: `greetings`, `family_people`, `body`, `numbers`,
`time_days`, `food_market`, `travel_places`, `everyday_verbs`, `wisdom`.

Audio: `seed/placeholder_audio.py` generates a TTS file per item and sets
`audio_state = 'placeholder'`. Real recordings later flip rows to `'verified'`
by updating `audio_url` — no schema change, and the admin panel can filter on
`audio_state = 'placeholder'` to give you a recording worklist for your next
Nigeria trip.

---

## 4. Phase 1 build order

Each step is deployable and testable before the next begins.

1. **Schema + seed** — Postgres up, 157 rows in, `SELECT` sanity checks. *(done)*
2. **Backend read path** — `/content` endpoints + track resolver, containerised, CI green, image published to GHCR. Testable with curl, no UI. *(done — 33 tests)*
3. **Auth + onboarding** — Supabase Auth, 8 screens, skip and resume, Settings edit. First thing a real user touches.
4. **Study modes** — flashcard → quiz → phrase practice → proverbs, in that order. Audio button and flag button ship with the first mode, not later.
5. **Progress, streak, share link** — the retention loop.
6. **Admin panel** — flag queue, edit, verify, contributor permissions.
7. **PWA polish + reminders** — installable, offline cache of today's unit, push.

Nothing from Phase 2 gets discussed until step 7 is live with real users.

---

## 5. Tone policy (decided)

**Option 2: phrases and proverbs carry tone marking, words stay plain.**

Declared in `content/ibo/language.yaml` under `tone_policy`, enforced by
`seed.py` as a *warning* rather than an error — the policy is per language and
will differ for Yoruba, so it should never hard-fail a load.

`target_text_toned` is a column on `content_items`: **one value per row, never
per lexeme.** The same word toned inside a proverb and toned as a standalone
vocabulary item are independent values, which is the only correct model for a
tonal language. The trade-off is that nothing checks consistency across rows;
`content_revisions` gives you the audit trail instead.

All 100 phrase and proverb rows currently have `target_text_toned` blank.
Machine-generated diacritics would be worse than nothing for the native-speaker
segment, so tone marking is a contributor task:

```bash
python db/seed/export_worklist.py -l ibo -t tone   # 100 rows, one blank column
```

The contributor fills one column offline in Excel; you paste it back into the
CSV on `source_key` and re-seed. `seed.py` fills `target_text_toned` when blank
and **never blanks it once set**, so a re-seed cannot destroy their work.

---

## 6. Authenticated authorization boundary

Every user-owned SQL operation behind `/v1/me`, `/v1/study`, and content-flag
writes is scoped by the user's UUID extracted from a locally verified
authentication token. The API never accepts a user ID from request input for
these operations.

Row-level security is intentionally deferred while the service-role API is the
sole database client. The service role bypasses RLS, so enabling policies now
would imply a protection boundary they do not provide. Authorization is
therefore enforced by the API's token-derived UUID at every user-owned query.

---

## 7. Study write path

An answer batch is one database transaction. Client answer IDs are immutable
per-user idempotency claims in the same transaction as progress, daily
activity, and aggregate stats, so a failed flush can be retried without losing
or double-counting work. Progress rows are locked in content-ID order and
streak dates are resolved in the learner's IANA timezone.

Content flags are scoped independently to either the item or one explanation
language. Their existing trigger remains the sole owner of `flag_count`, with
mutations serialized on the content row. Public share profiles use a separate
six-field projection and never expose user IDs, email, preferences, progress,
flags, or exact timestamps.
