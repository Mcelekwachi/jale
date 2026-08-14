-- =====================================================================
-- Jalɛ — Phase 1 schema
-- PostgreSQL 15+ (Supabase-compatible)
--
-- Design rule: adding Yoruba = INSERT rows into languages/categories/
-- content_items/tracks. No new tables, no new columns, no code change.
-- =====================================================================

-- gen_random_uuid() is built in from PG13, so pgcrypto is not required.
-- pg_trgm powers fuzzy search on target_text in the admin panel. It ships with
-- Supabase, Railway and Render but not with every minimal build, so it is
-- optional: without it the schema still applies and search falls back to LIKE.
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS "pg_trgm";
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'pg_trgm unavailable — fuzzy search index will be skipped';
END $$;

-- ---------------------------------------------------------------------
-- 1. ENUMS
-- Closed-ish sets. Extending is a one-liner: ALTER TYPE x ADD VALUE 'y';
-- ---------------------------------------------------------------------

DO $$ BEGIN CREATE TYPE content_type AS ENUM ('word', 'phrase', 'proverb', 'story');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE difficulty_level AS ENUM ('beginner', 'intermediate', 'advanced', 'native');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE content_status AS ENUM ('draft', 'published', 'hidden');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE audio_status AS ENUM ('missing', 'placeholder', 'verified');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE user_role AS ENUM ('learner', 'contributor', 'validator', 'admin');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE contributor_status AS ENUM ('active', 'paused', 'suspended');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE contributor_level AS ENUM ('learner', 'speaker', 'keeper', 'elder');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE validator_status AS ENUM ('not_applicable', 'pending_verification', 'verified', 'suspended');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE validator_level AS ENUM ('standard', 'senior');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE payment_provider AS ENUM ('paystack', 'wise');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE submission_status AS ENUM ('pending', 'in_review', 'accepted', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE validator_decision AS ENUM ('approve', 'reject');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE earnings_role AS ENUM ('contributor', 'validator');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE earnings_status AS ENUM ('pending', 'paid', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE submission_kind AS ENUM ('new_content', 'correction', 'dialect_variant', 'audio');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE age_band AS ENUM ('child_u13', 'young_adult_13_25', 'adult_25_plus');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE connection_type AS ENUM (
  'complete_beginner', 'language_enthusiast', 'connected_to_igbo_family',
  'igbo_heritage_speaker', 'igbo_parent_abroad', 'mixed_parent_abroad',
  'aboriginal_native', 'other_african_heritage');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE learning_goal AS ENUM (
  'family_and_culture', 'teach_my_children', 'visiting_nigeria',
  'academic_professional', 'cultural_pride', 'new_language', 'improve_proverbs_vocab');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE learning_style AS ENUM ('game_points', 'structured_lessons', 'mixed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE study_mode AS ENUM ('flashcard', 'quiz', 'phrase_practice', 'proverbs');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE flag_reason AS ENUM (
  'bad_audio', 'wrong_translation', 'cultural_inaccuracy',
  'spelling_or_tone', 'offensive', 'other');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE flag_status AS ENUM ('open', 'in_review', 'resolved', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------
-- 2. LANGUAGE LAYER
-- The whole multi-language promise lives here.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS languages (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,          -- ISO 639-3: 'ibo', 'yor', 'hau'
  name          TEXT NOT NULL,                 -- 'Igbo'
  endonym       TEXT,                          -- 'Asụsụ Igbo'
  flag_emoji    TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT FALSE,-- available for use in the app
  is_learnable  BOOLEAN NOT NULL DEFAULT FALSE,
  is_meta       BOOLEAN NOT NULL DEFAULT FALSE,
  -- Founder-only Phase 1 uses 1; raise to 3 per language after validators are recruited.
  required_validators SMALLINT NOT NULL DEFAULT 1,
  sort_order    SMALLINT NOT NULL DEFAULT 100,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE languages
  ADD COLUMN IF NOT EXISTS id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS code TEXT NOT NULL UNIQUE,
  ADD COLUMN IF NOT EXISTS name TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS endonym TEXT,
  ADD COLUMN IF NOT EXISTS flag_emoji TEXT,
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS is_learnable BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS is_meta BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS required_validators SMALLINT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS sort_order SMALLINT NOT NULL DEFAULT 100,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS dialects (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  language_id   SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  code          TEXT NOT NULL,                 -- 'central'
  name          TEXT NOT NULL,                 -- 'Central Igbo'
  is_default    BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (language_id, code)
);
ALTER TABLE dialects
  ADD COLUMN IF NOT EXISTS id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS language_id SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS code TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS name TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS one_default_dialect_per_language
  ON dialects (language_id) WHERE is_default;

-- Categories are per-language so Yoruba can have its own taxonomy,
-- but a shared slug ('greetings') keeps cross-language UI code generic.
CREATE TABLE IF NOT EXISTS categories (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  language_id   SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  slug          TEXT NOT NULL,                 -- 'greetings', 'family', 'body', 'numbers'
  name          TEXT NOT NULL,                 -- 'Greetings & Courtesy'
  icon          TEXT,
  sort_order    SMALLINT NOT NULL DEFAULT 100,
  UNIQUE (language_id, slug)
);
ALTER TABLE categories
  ADD COLUMN IF NOT EXISTS id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS language_id SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS slug TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS name TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS icon TEXT,
  ADD COLUMN IF NOT EXISTS sort_order SMALLINT NOT NULL DEFAULT 100;

-- ---------------------------------------------------------------------
-- 3. CONTENT
-- One table for words, phrases, proverbs and (Phase 2) stories.
-- NOTE: column is target_text, NOT igbo_text — see ARCHITECTURE.md.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS content_items (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

  -- stable natural key for idempotent re-seeding: 'ibo:word:ndewo'
  source_key          TEXT NOT NULL UNIQUE,

  language_id         SMALLINT NOT NULL REFERENCES languages(id),
  dialect_id          SMALLINT REFERENCES dialects(id),
  category_id         SMALLINT REFERENCES categories(id),

  content_type        content_type NOT NULL,
  difficulty_level    difficulty_level NOT NULL DEFAULT 'beginner',

  target_text         TEXT NOT NULL,           -- 'Ndewo'
  target_text_toned   TEXT,                    -- tone-marked variant, nullable
  example_sentence    TEXT,
  example_translation TEXT,

  audio_url           TEXT,
  audio_state         audio_status NOT NULL DEFAULT 'missing',

  status              content_status NOT NULL DEFAULT 'published',
  verified            BOOLEAN NOT NULL DEFAULT FALSE,
  verified_by         UUID,                    -- FK added after app_users
  verified_at         TIMESTAMPTZ,
  contributor_id      UUID,                    -- FK added after app_users

  flag_count          INTEGER NOT NULL DEFAULT 0,
  sort_order          INTEGER NOT NULL DEFAULT 100,

  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE content_items
  ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS source_key TEXT NOT NULL UNIQUE,
  ADD COLUMN IF NOT EXISTS language_id SMALLINT NOT NULL REFERENCES languages(id),
  ADD COLUMN IF NOT EXISTS dialect_id SMALLINT REFERENCES dialects(id),
  ADD COLUMN IF NOT EXISTS category_id SMALLINT REFERENCES categories(id),
  ADD COLUMN IF NOT EXISTS content_type content_type NOT NULL,
  ADD COLUMN IF NOT EXISTS difficulty_level difficulty_level NOT NULL DEFAULT 'beginner',
  ADD COLUMN IF NOT EXISTS target_text TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS target_text_toned TEXT,
  ADD COLUMN IF NOT EXISTS example_sentence TEXT,
  ADD COLUMN IF NOT EXISTS example_translation TEXT,
  ADD COLUMN IF NOT EXISTS audio_url TEXT,
  ADD COLUMN IF NOT EXISTS audio_state audio_status NOT NULL DEFAULT 'missing',
  ADD COLUMN IF NOT EXISTS status content_status NOT NULL DEFAULT 'published',
  ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS verified_by UUID,
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS contributor_id UUID,
  ADD COLUMN IF NOT EXISTS flag_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 100,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- prevents accidental duplicates when seeding, e.g. "Ndewo" twice as a word
CREATE UNIQUE INDEX IF NOT EXISTS content_items_natural_uniq
  ON content_items (language_id, content_type, lower(target_text));

CREATE INDEX IF NOT EXISTS content_items_browse_idx
  ON content_items (language_id, content_type, difficulty_level, status);
CREATE INDEX IF NOT EXISTS content_items_category_idx ON content_items (category_id);
CREATE INDEX IF NOT EXISTS content_items_flagged_idx
  ON content_items (flag_count DESC) WHERE flag_count > 0;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
    CREATE INDEX IF NOT EXISTS content_items_search_idx
      ON content_items USING gin (target_text gin_trgm_ops);
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- 4. USERS
-- app_users.id mirrors Supabase auth.users.id. Auth stays in Supabase.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS app_users (
  id            UUID PRIMARY KEY,              -- = auth.uid()
  email         TEXT,
  display_name  TEXT,
  avatar_url    TEXT,
  role          user_role NOT NULL DEFAULT 'learner',
  share_slug    TEXT UNIQUE,                   -- /u/ndubuisi-9f3a
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at  TIMESTAMPTZ
);
ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS id UUID PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS email TEXT,
  ADD COLUMN IF NOT EXISTS display_name TEXT,
  ADD COLUMN IF NOT EXISTS avatar_url TEXT,
  ADD COLUMN IF NOT EXISTS role user_role NOT NULL DEFAULT 'learner',
  ADD COLUMN IF NOT EXISTS share_slug TEXT UNIQUE,
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'content_items_contributor_fk'
       AND conrelid = 'content_items'::regclass
  ) THEN
    ALTER TABLE content_items ADD CONSTRAINT content_items_contributor_fk
      FOREIGN KEY (contributor_id) REFERENCES app_users(id) ON DELETE SET NULL;
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'content_items_verifier_fk'
       AND conrelid = 'content_items'::regclass
  ) THEN
    ALTER TABLE content_items ADD CONSTRAINT content_items_verifier_fk
      FOREIGN KEY (verified_by) REFERENCES app_users(id) ON DELETE SET NULL;
  END IF;
END $$;

-- Translations are keyed by content and meta-language so adding an explanation
-- language does not duplicate the target-language content.
CREATE TABLE IF NOT EXISTS content_translations (
  content_id          BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  meta_language_id    SMALLINT NOT NULL REFERENCES languages(id),
  translation         TEXT NOT NULL,
  literal_translation TEXT,
  cultural_note       TEXT,
  verified            BOOLEAN NOT NULL DEFAULT FALSE,
  verified_by         UUID REFERENCES app_users(id) ON DELETE SET NULL,
  verified_at         TIMESTAMPTZ,
  contributor_id      UUID REFERENCES app_users(id) ON DELETE SET NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (content_id, meta_language_id)
);
ALTER TABLE content_translations
  ADD COLUMN IF NOT EXISTS content_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS meta_language_id SMALLINT NOT NULL REFERENCES languages(id),
  ADD COLUMN IF NOT EXISTS translation TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS literal_translation TEXT,
  ADD COLUMN IF NOT EXISTS cultural_note TEXT,
  ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS verified_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS contributor_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Which languages a contributor is trusted for (Phase 2 uses it, Phase 1
-- just needs the row to exist so permissions aren't a code change later).
CREATE TABLE IF NOT EXISTS contributor_permissions (
  user_id       UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  language_id   SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  can_verify    BOOLEAN NOT NULL DEFAULT FALSE,
  granted_by    UUID REFERENCES app_users(id),
  granted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, language_id)
);
ALTER TABLE contributor_permissions
  ADD COLUMN IF NOT EXISTS user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS language_id SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS can_verify BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS granted_by UUID REFERENCES app_users(id),
  ADD COLUMN IF NOT EXISTS granted_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Contributor identity, trust and payout-recipient metadata. Payment providers
-- retain all bank/payment credentials; only their recipient token is stored.
CREATE TABLE IF NOT EXISTS contributors (
  id                           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id                      UUID NOT NULL UNIQUE REFERENCES app_users(id) ON DELETE CASCADE,
  display_name                 TEXT NOT NULL,
  location                     TEXT,
  payment_provider             payment_provider,
  payment_recipient_token      TEXT,
  payment_last_four            TEXT,
  payment_currency             CHAR(3),
  contributor_level            contributor_level NOT NULL DEFAULT 'learner',
  total_earnings_cents         BIGINT NOT NULL DEFAULT 0,
  total_accepted_batches       INTEGER NOT NULL DEFAULT 0,
  total_rejected_batches       INTEGER NOT NULL DEFAULT 0,
  consecutive_rejected_batches INTEGER NOT NULL DEFAULT 0,
  validator_status             validator_status NOT NULL DEFAULT 'not_applicable',
  validator_level              validator_level,
  validator_verified_at        TIMESTAMPTZ,
  validator_verified_by        UUID REFERENCES app_users(id),
  validator_verification_note  TEXT,
  status                       contributor_status NOT NULL DEFAULT 'active',
  status_reason                TEXT,
  -- Consent is separate, explicit and revocable; elder status never publishes identity.
  public_listing_consent       BOOLEAN NOT NULL DEFAULT FALSE,
  joined_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT contributor_validator_level_verified CHECK (
    validator_status = 'verified' OR validator_level IS NULL
  ),
  CONSTRAINT contributor_validator_verification_pair CHECK (
    (validator_verified_at IS NULL AND validator_verified_by IS NULL)
    OR (
      validator_status = 'verified'
      AND validator_verified_at IS NOT NULL
      AND validator_verified_by IS NOT NULL
    )
  )
);
ALTER TABLE contributors
  ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS user_id UUID NOT NULL UNIQUE REFERENCES app_users(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS location TEXT,
  ADD COLUMN IF NOT EXISTS payment_provider payment_provider,
  ADD COLUMN IF NOT EXISTS payment_recipient_token TEXT,
  ADD COLUMN IF NOT EXISTS payment_last_four TEXT,
  ADD COLUMN IF NOT EXISTS payment_currency CHAR(3),
  ADD COLUMN IF NOT EXISTS contributor_level contributor_level NOT NULL DEFAULT 'learner',
  ADD COLUMN IF NOT EXISTS total_earnings_cents BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_accepted_batches INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_rejected_batches INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS consecutive_rejected_batches INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS validator_status validator_status NOT NULL DEFAULT 'not_applicable',
  ADD COLUMN IF NOT EXISTS validator_level validator_level,
  ADD COLUMN IF NOT EXISTS validator_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS validator_verified_by UUID REFERENCES app_users(id),
  ADD COLUMN IF NOT EXISTS validator_verification_note TEXT,
  ADD COLUMN IF NOT EXISTS status contributor_status NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS status_reason TEXT,
  ADD COLUMN IF NOT EXISTS public_listing_consent BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS content_submissions (
  id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  contributor_id           BIGINT NOT NULL REFERENCES contributors(id),
  language_id              SMALLINT NOT NULL REFERENCES languages(id),
  dialect_id               SMALLINT REFERENCES dialects(id),
  category_id              SMALLINT REFERENCES categories(id),
  submission_kind          submission_kind NOT NULL,
  content_type             content_type NOT NULL,
  difficulty_level         difficulty_level,
  target_text              TEXT NOT NULL,
  target_text_toned        TEXT,
  meta_language_id         SMALLINT REFERENCES languages(id),
  translation              TEXT,
  literal_translation      TEXT,
  cultural_note            TEXT,
  example_sentence         TEXT,
  audio_url                TEXT,
  corrects_content_id      BIGINT REFERENCES content_items(id),
  batch_id                 UUID,
  status                   submission_status NOT NULL DEFAULT 'pending',
  rejection_reason         TEXT,
  duplicate_of_content_id  BIGINT REFERENCES content_items(id),
  published_content_id     BIGINT REFERENCES content_items(id),
  submitted_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at               TIMESTAMPTZ,
  paid_at                  TIMESTAMPTZ,
  payment_amount_cents     INTEGER,
  CONSTRAINT submission_correction_target CHECK (
    (submission_kind IN ('correction', 'dialect_variant') AND corrects_content_id IS NOT NULL)
    OR (submission_kind = 'new_content' AND corrects_content_id IS NULL)
    OR submission_kind = 'audio'
  )
);
ALTER TABLE content_submissions
  ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS contributor_id BIGINT NOT NULL REFERENCES contributors(id),
  ADD COLUMN IF NOT EXISTS language_id SMALLINT NOT NULL REFERENCES languages(id),
  ADD COLUMN IF NOT EXISTS dialect_id SMALLINT REFERENCES dialects(id),
  ADD COLUMN IF NOT EXISTS category_id SMALLINT REFERENCES categories(id),
  ADD COLUMN IF NOT EXISTS submission_kind submission_kind NOT NULL,
  ADD COLUMN IF NOT EXISTS content_type content_type NOT NULL,
  ADD COLUMN IF NOT EXISTS difficulty_level difficulty_level,
  ADD COLUMN IF NOT EXISTS target_text TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS target_text_toned TEXT,
  ADD COLUMN IF NOT EXISTS meta_language_id SMALLINT REFERENCES languages(id),
  ADD COLUMN IF NOT EXISTS translation TEXT,
  ADD COLUMN IF NOT EXISTS literal_translation TEXT,
  ADD COLUMN IF NOT EXISTS cultural_note TEXT,
  ADD COLUMN IF NOT EXISTS example_sentence TEXT,
  ADD COLUMN IF NOT EXISTS audio_url TEXT,
  ADD COLUMN IF NOT EXISTS corrects_content_id BIGINT REFERENCES content_items(id),
  ADD COLUMN IF NOT EXISTS batch_id UUID,
  ADD COLUMN IF NOT EXISTS status submission_status NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
  ADD COLUMN IF NOT EXISTS duplicate_of_content_id BIGINT REFERENCES content_items(id),
  ADD COLUMN IF NOT EXISTS published_content_id BIGINT REFERENCES content_items(id),
  ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS payment_amount_cents INTEGER;
CREATE INDEX IF NOT EXISTS content_submissions_contributor_status_idx
  ON content_submissions (contributor_id, status);
CREATE INDEX IF NOT EXISTS content_submissions_status_submitted_idx
  ON content_submissions (status, submitted_at);
CREATE INDEX IF NOT EXISTS content_submissions_batch_idx ON content_submissions (batch_id);

CREATE TABLE IF NOT EXISTS validator_assignments (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  submission_id      BIGINT NOT NULL REFERENCES content_submissions(id) ON DELETE CASCADE,
  validator_id       BIGINT NOT NULL REFERENCES contributors(id),
  decision           validator_decision,
  correction_note    TEXT,
  counts_for_payment BOOLEAN NOT NULL DEFAULT TRUE,
  assigned_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at         TIMESTAMPTZ,
  UNIQUE (submission_id, validator_id),
  CONSTRAINT validator_assignment_decision_time CHECK (
    (decision IS NULL) = (decided_at IS NULL)
  )
);
ALTER TABLE validator_assignments
  ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS submission_id BIGINT NOT NULL REFERENCES content_submissions(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS validator_id BIGINT NOT NULL REFERENCES contributors(id),
  ADD COLUMN IF NOT EXISTS decision validator_decision,
  ADD COLUMN IF NOT EXISTS correction_note TEXT,
  ADD COLUMN IF NOT EXISTS counts_for_payment BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS earnings_ledger (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  contributor_id      BIGINT NOT NULL REFERENCES contributors(id),
  role                earnings_role NOT NULL,
  batch_reference     TEXT NOT NULL UNIQUE,
  item_count          INTEGER NOT NULL,
  rate_description    TEXT NOT NULL,
  amount_eur_cents    INTEGER NOT NULL,
  payout_currency     CHAR(3),
  payout_amount_minor BIGINT,
  exchange_rate       NUMERIC(18,8),
  payment_provider    payment_provider,
  payment_reference   TEXT,
  status              earnings_status NOT NULL DEFAULT 'pending',
  failure_reason      TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at             TIMESTAMPTZ
);
ALTER TABLE earnings_ledger
  ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS contributor_id BIGINT NOT NULL REFERENCES contributors(id),
  ADD COLUMN IF NOT EXISTS role earnings_role NOT NULL,
  ADD COLUMN IF NOT EXISTS batch_reference TEXT NOT NULL UNIQUE,
  ADD COLUMN IF NOT EXISTS item_count INTEGER NOT NULL,
  ADD COLUMN IF NOT EXISTS rate_description TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS amount_eur_cents INTEGER NOT NULL,
  ADD COLUMN IF NOT EXISTS payout_currency CHAR(3),
  ADD COLUMN IF NOT EXISTS payout_amount_minor BIGINT,
  ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(18,8),
  ADD COLUMN IF NOT EXISTS payment_provider payment_provider,
  ADD COLUMN IF NOT EXISTS payment_reference TEXT,
  ADD COLUMN IF NOT EXISTS status earnings_status NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS failure_reason TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;

-- ---------------------------------------------------------------------
-- 5. ONBOARDING / PREFERENCES
-- One row per user. Written once, editable forever from Settings.
-- Every answer is nullable because onboarding is skippable at any screen.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id             UUID PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  active_language_id  SMALLINT REFERENCES languages(id),
  meta_language_id    SMALLINT REFERENCES languages(id),
  active_dialect_id   SMALLINT REFERENCES dialects(id),

  age_band            age_band,
  connection          connection_type,
  goal                learning_goal,
  style               learning_style,
  daily_minutes       SMALLINT CHECK (daily_minutes IN (5, 15, 30)),

  reminder_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
  reminder_time       TIME,
  timezone            TEXT NOT NULL DEFAULT 'UTC',

  placement_level     difficulty_level,        -- from the 3-question quiz
  placement_skipped   BOOLEAN NOT NULL DEFAULT FALSE,

  onboarding_status   TEXT NOT NULL DEFAULT 'not_started'
                      CHECK (onboarding_status IN ('not_started','skipped','completed')),
  onboarding_last_screen SMALLINT,             -- resume point if abandoned
  completed_at        TIMESTAMPTZ,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE user_preferences
  ADD COLUMN IF NOT EXISTS user_id UUID PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS active_language_id SMALLINT REFERENCES languages(id),
  ADD COLUMN IF NOT EXISTS meta_language_id SMALLINT REFERENCES languages(id),
  ADD COLUMN IF NOT EXISTS active_dialect_id SMALLINT REFERENCES dialects(id),
  ADD COLUMN IF NOT EXISTS age_band age_band,
  ADD COLUMN IF NOT EXISTS connection connection_type,
  ADD COLUMN IF NOT EXISTS goal learning_goal,
  ADD COLUMN IF NOT EXISTS style learning_style,
  ADD COLUMN IF NOT EXISTS daily_minutes SMALLINT CHECK (daily_minutes IN (5, 15, 30)),
  ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS reminder_time TIME,
  ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC',
  ADD COLUMN IF NOT EXISTS placement_level difficulty_level,
  ADD COLUMN IF NOT EXISTS placement_skipped BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS onboarding_status TEXT NOT NULL DEFAULT 'not_started'
    CHECK (onboarding_status IN ('not_started','skipped','completed')),
  ADD COLUMN IF NOT EXISTS onboarding_last_screen SMALLINT,
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ---------------------------------------------------------------------
-- 6. CURRICULUM TRACKS
-- The persona -> curriculum mapping is DATA, not an if/else ladder.
-- Adding "Yoruba heritage speaker" later = 1 track + 1 rule + N units.
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tracks (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  language_id   SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  slug          TEXT NOT NULL,                 -- 'ibo_native_advanced'
  name          TEXT NOT NULL,                 -- 'Proverbs & Formal Igbo'
  description   TEXT,
  min_difficulty difficulty_level NOT NULL DEFAULT 'beginner',
  max_difficulty difficulty_level NOT NULL DEFAULT 'native',
  is_default    BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (language_id, slug)
);
ALTER TABLE tracks
  ADD COLUMN IF NOT EXISTS id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS language_id SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS slug TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS name TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS min_difficulty difficulty_level NOT NULL DEFAULT 'beginner',
  ADD COLUMN IF NOT EXISTS max_difficulty difficulty_level NOT NULL DEFAULT 'native',
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;

-- First matching rule (lowest priority number) wins. NULL = wildcard.
CREATE TABLE IF NOT EXISTS track_rules (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  track_id      SMALLINT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  priority      SMALLINT NOT NULL,
  match_age     age_band[],                    -- NULL = any
  match_connection connection_type[],
  match_goal    learning_goal[],
  match_style   learning_style[],
  UNIQUE (track_id, priority)
);
ALTER TABLE track_rules
  ADD COLUMN IF NOT EXISTS id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS track_id SMALLINT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL,
  ADD COLUMN IF NOT EXISTS match_age age_band[],
  ADD COLUMN IF NOT EXISTS match_connection connection_type[],
  ADD COLUMN IF NOT EXISTS match_goal learning_goal[],
  ADD COLUMN IF NOT EXISTS match_style learning_style[];

-- The ordered syllabus. Each unit is a content query, not a content list,
-- so newly added/verified items flow into existing tracks automatically.
CREATE TABLE IF NOT EXISTS track_units (
  id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  track_id        SMALLINT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  position        SMALLINT NOT NULL,
  title           TEXT NOT NULL,               -- 'Greetings & First Words'
  mode            study_mode NOT NULL,
  filter_category_id  SMALLINT REFERENCES categories(id),
  filter_content_type content_type,
  filter_difficulty   difficulty_level,
  item_count      SMALLINT NOT NULL DEFAULT 10,
  UNIQUE (track_id, position)
);
ALTER TABLE track_units
  ADD COLUMN IF NOT EXISTS id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS track_id SMALLINT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS position SMALLINT NOT NULL,
  ADD COLUMN IF NOT EXISTS title TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS mode study_mode NOT NULL,
  ADD COLUMN IF NOT EXISTS filter_category_id SMALLINT REFERENCES categories(id),
  ADD COLUMN IF NOT EXISTS filter_content_type content_type,
  ADD COLUMN IF NOT EXISTS filter_difficulty difficulty_level,
  ADD COLUMN IF NOT EXISTS item_count SMALLINT NOT NULL DEFAULT 10;

-- ---------------------------------------------------------------------
-- 7. PROGRESS, STREAKS
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_progress (
  user_id           UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  content_id        BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  times_seen        INTEGER NOT NULL DEFAULT 0,
  times_correct     INTEGER NOT NULL DEFAULT 0,
  times_incorrect   INTEGER NOT NULL DEFAULT 0,
  leitner_box       SMALLINT NOT NULL DEFAULT 0,   -- 0..5, simplest SRS
  due_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  mastered          BOOLEAN NOT NULL DEFAULT FALSE,
  first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_reviewed_at  TIMESTAMPTZ,
  PRIMARY KEY (user_id, content_id)
);
ALTER TABLE user_progress
  ADD COLUMN IF NOT EXISTS user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS content_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS times_seen INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS times_correct INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS times_incorrect INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS leitner_box SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS mastered BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS last_reviewed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS user_progress_due_idx ON user_progress (user_id, due_at);

-- Immutable client-generated answer claims make retries safe.  The content
-- reference deliberately keeps the original item identity for conflict checks.
CREATE TABLE IF NOT EXISTS study_answer_receipts (
  user_id          UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  client_answer_id TEXT NOT NULL,
  content_id       BIGINT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, client_answer_id)
);
ALTER TABLE study_answer_receipts
  ADD COLUMN IF NOT EXISTS user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS client_answer_id TEXT NOT NULL,
  ADD COLUMN IF NOT EXISTS content_id BIGINT NOT NULL,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Source of truth for the streak. One row per active day.
CREATE TABLE IF NOT EXISTS user_daily_activity (
  user_id         UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  activity_date   DATE NOT NULL,               -- in the user's local timezone
  items_reviewed  INTEGER NOT NULL DEFAULT 0,
  seconds_spent   INTEGER NOT NULL DEFAULT 0,
  xp              INTEGER NOT NULL DEFAULT 0,
  goal_met        BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (user_id, activity_date)
);
ALTER TABLE user_daily_activity
  ADD COLUMN IF NOT EXISTS user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS activity_date DATE NOT NULL,
  ADD COLUMN IF NOT EXISTS items_reviewed INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS seconds_spent INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS xp INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS goal_met BOOLEAN NOT NULL DEFAULT FALSE;

-- Denormalised for fast profile/share-page reads.
CREATE TABLE IF NOT EXISTS user_stats (
  user_id            UUID PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  current_streak     INTEGER NOT NULL DEFAULT 0,
  longest_streak     INTEGER NOT NULL DEFAULT 0,
  last_activity_date DATE,
  total_items_seen   INTEGER NOT NULL DEFAULT 0,
  total_mastered     INTEGER NOT NULL DEFAULT 0,
  total_xp           INTEGER NOT NULL DEFAULT 0,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE user_stats
  ADD COLUMN IF NOT EXISTS user_id UUID PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS current_streak INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS longest_streak INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_activity_date DATE,
  ADD COLUMN IF NOT EXISTS total_items_seen INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_mastered INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_xp INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ---------------------------------------------------------------------
-- 8. FLAGS & MODERATION
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS content_flags (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content_id      BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  user_id         UUID REFERENCES app_users(id) ON DELETE SET NULL,
  meta_language_id SMALLINT REFERENCES languages(id),
  reason          flag_reason NOT NULL,
  note            TEXT,
  status          flag_status NOT NULL DEFAULT 'open',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_by     UUID REFERENCES app_users(id),
  resolved_at     TIMESTAMPTZ,
  resolution_note TEXT
);
ALTER TABLE content_flags
  ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS content_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS meta_language_id SMALLINT REFERENCES languages(id),
  ADD COLUMN IF NOT EXISTS reason flag_reason NOT NULL,
  ADD COLUMN IF NOT EXISTS note TEXT,
  ADD COLUMN IF NOT EXISTS status flag_status NOT NULL DEFAULT 'open',
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS resolved_by UUID REFERENCES app_users(id),
  ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resolution_note TEXT;
-- one open flag per user per item and meta-language scope
CREATE UNIQUE INDEX IF NOT EXISTS one_open_flag_per_user
  ON content_flags (content_id, user_id, COALESCE(meta_language_id, 0))
  WHERE status IN ('open', 'in_review');

-- Audit trail for every edit an admin or contributor makes.
CREATE TABLE IF NOT EXISTS content_revisions (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content_id    BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  changed_by    UUID REFERENCES app_users(id) ON DELETE SET NULL,
  change_note   TEXT,
  before_state  JSONB NOT NULL,
  after_state   JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE content_revisions
  ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ADD COLUMN IF NOT EXISTS content_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS changed_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS change_note TEXT,
  ADD COLUMN IF NOT EXISTS before_state JSONB NOT NULL,
  ADD COLUMN IF NOT EXISTS after_state JSONB NOT NULL,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- ---------------------------------------------------------------------
-- 9. TRIGGERS
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS content_items_touch ON content_items;
CREATE TRIGGER content_items_touch BEFORE UPDATE ON content_items
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
DROP TRIGGER IF EXISTS content_translations_touch ON content_translations;
CREATE TRIGGER content_translations_touch BEFORE UPDATE ON content_translations
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
DROP TRIGGER IF EXISTS user_preferences_touch ON user_preferences;
CREATE TRIGGER user_preferences_touch BEFORE UPDATE ON user_preferences
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
DROP TRIGGER IF EXISTS contributors_touch ON contributors;
CREATE TRIGGER contributors_touch BEFORE UPDATE ON contributors
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- The seeded English/default proverb translation must carry its cultural lesson;
-- other meta languages may fall back to that lesson independently.
CREATE OR REPLACE FUNCTION require_proverb_translation_cultural_note()
RETURNS TRIGGER AS $$
DECLARE
  parent_type content_type;
  translation_language CHAR(3);
BEGIN
  SELECT content_type INTO parent_type
    FROM content_items
   WHERE id = NEW.content_id;

  SELECT code INTO translation_language
    FROM languages
   WHERE id = NEW.meta_language_id;

  IF parent_type = 'proverb'
     AND translation_language = 'eng'
     AND NEW.cultural_note IS NULL THEN
    RAISE EXCEPTION 'cultural_note is required for proverb translations';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS content_translations_require_proverb_note ON content_translations;
CREATE TRIGGER content_translations_require_proverb_note
  BEFORE INSERT OR UPDATE ON content_translations
  FOR EACH ROW EXECUTE FUNCTION require_proverb_translation_cultural_note();

CREATE OR REPLACE FUNCTION require_submission_proverb_cultural_note()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.content_type = 'proverb'
     AND NEW.translation IS NOT NULL
     AND NEW.cultural_note IS NULL THEN
    RAISE EXCEPTION 'cultural_note is required for translated proverb submissions';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS content_submissions_require_proverb_note ON content_submissions;
CREATE TRIGGER content_submissions_require_proverb_note
  BEFORE INSERT OR UPDATE ON content_submissions
  FOR EACH ROW EXECUTE FUNCTION require_submission_proverb_cultural_note();

-- keep content_items.flag_count in sync with open flags
CREATE OR REPLACE FUNCTION sync_flag_count() RETURNS TRIGGER AS $$
DECLARE target BIGINT;
BEGIN
  target := COALESCE(NEW.content_id, OLD.content_id);
  UPDATE content_items c
     SET flag_count = (
       SELECT count(*) FROM content_flags f
        WHERE f.content_id = target AND f.status IN ('open','in_review'))
   WHERE c.id = target;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS content_flags_sync ON content_flags;
CREATE TRIGGER content_flags_sync
  AFTER INSERT OR UPDATE OR DELETE ON content_flags
  FOR EACH ROW EXECUTE FUNCTION sync_flag_count();

-- ---------------------------------------------------------------------
-- 10. ADMIN VIEW — the flag review queue
-- ---------------------------------------------------------------------

DROP VIEW IF EXISTS admin_flag_queue;
CREATE VIEW admin_flag_queue AS
SELECT c.id            AS content_id,
       l.code          AS language,
       c.content_type,
       c.target_text,
       default_ct.translation,
       f.status,
       count(f.id)::INTEGER AS flag_count,
       min(f.created_at) AS oldest_flag_at,
       array_agg(DISTINCT f.reason::text ORDER BY f.reason::text) AS reasons,
       count(DISTINCT f.user_id)::INTEGER AS reporter_count,
       jsonb_agg(jsonb_build_object(
         'id', f.id,
         'reason', f.reason,
         'note', f.note,
         'reporter_id', f.user_id,
         'status', f.status,
         'created_at', f.created_at,
         'meta_language', ml.code
       ) ORDER BY f.created_at, f.id) AS flags
  FROM content_items c
  JOIN languages l ON l.id = c.language_id
  JOIN content_flags f ON f.content_id = c.id
  LEFT JOIN languages ml ON ml.id = f.meta_language_id
  LEFT JOIN languages default_ml ON default_ml.code = 'eng' AND default_ml.is_meta
  LEFT JOIN content_translations default_ct
    ON default_ct.content_id = c.id AND default_ct.meta_language_id = default_ml.id
 GROUP BY c.id, l.code, default_ct.translation, f.status
 ORDER BY count(f.id) DESC, oldest_flag_at ASC;

-- ---------------------------------------------------------------------
-- 11. ROW LEVEL SECURITY (enable when wired to Supabase Auth)
-- Content is world-readable when published; user rows are self-only;
-- writes to content go through the FastAPI service role only.
-- ---------------------------------------------------------------------
-- ALTER TABLE user_progress        ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE user_preferences     ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE user_daily_activity  ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE user_stats           ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY self_rw ON user_progress
--   USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- ---------------------------------------------------------------------
-- ONE-OFF COLUMN TYPE / DEFAULT CHANGES
-- Renames and data backfills do not fit the rerunnable schema pattern. Any
-- future ALTER COLUMN statement added here must itself be safe to re-run.
-- This section is intentionally empty.
-- ---------------------------------------------------------------------

-- ENUM VALUE UPGRADES — keep at the end of the file
-- psycopg executes this multi-statement file as one implicit transaction.
-- PostgreSQL permits new enum values to be used only after that transaction
-- commits, so these statements must remain after every statement that can use
-- an enum value. The seed runs separately after schema application commits.
ALTER TYPE content_type ADD VALUE IF NOT EXISTS 'word';
ALTER TYPE content_type ADD VALUE IF NOT EXISTS 'phrase';
ALTER TYPE content_type ADD VALUE IF NOT EXISTS 'proverb';
ALTER TYPE content_type ADD VALUE IF NOT EXISTS 'story';
ALTER TYPE difficulty_level ADD VALUE IF NOT EXISTS 'beginner';
ALTER TYPE difficulty_level ADD VALUE IF NOT EXISTS 'intermediate';
ALTER TYPE difficulty_level ADD VALUE IF NOT EXISTS 'advanced';
ALTER TYPE difficulty_level ADD VALUE IF NOT EXISTS 'native';
ALTER TYPE content_status ADD VALUE IF NOT EXISTS 'draft';
ALTER TYPE content_status ADD VALUE IF NOT EXISTS 'published';
ALTER TYPE content_status ADD VALUE IF NOT EXISTS 'hidden';
ALTER TYPE audio_status ADD VALUE IF NOT EXISTS 'missing';
ALTER TYPE audio_status ADD VALUE IF NOT EXISTS 'placeholder';
ALTER TYPE audio_status ADD VALUE IF NOT EXISTS 'verified';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'learner';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'contributor';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'validator';
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'admin';
ALTER TYPE contributor_status ADD VALUE IF NOT EXISTS 'active';
ALTER TYPE contributor_status ADD VALUE IF NOT EXISTS 'paused';
ALTER TYPE contributor_status ADD VALUE IF NOT EXISTS 'suspended';
ALTER TYPE contributor_level ADD VALUE IF NOT EXISTS 'learner';
ALTER TYPE contributor_level ADD VALUE IF NOT EXISTS 'speaker';
ALTER TYPE contributor_level ADD VALUE IF NOT EXISTS 'keeper';
ALTER TYPE contributor_level ADD VALUE IF NOT EXISTS 'elder';
ALTER TYPE validator_status ADD VALUE IF NOT EXISTS 'not_applicable';
ALTER TYPE validator_status ADD VALUE IF NOT EXISTS 'pending_verification';
ALTER TYPE validator_status ADD VALUE IF NOT EXISTS 'verified';
ALTER TYPE validator_status ADD VALUE IF NOT EXISTS 'suspended';
ALTER TYPE validator_level ADD VALUE IF NOT EXISTS 'standard';
ALTER TYPE validator_level ADD VALUE IF NOT EXISTS 'senior';
ALTER TYPE payment_provider ADD VALUE IF NOT EXISTS 'paystack';
ALTER TYPE payment_provider ADD VALUE IF NOT EXISTS 'wise';
ALTER TYPE submission_status ADD VALUE IF NOT EXISTS 'pending';
ALTER TYPE submission_status ADD VALUE IF NOT EXISTS 'in_review';
ALTER TYPE submission_status ADD VALUE IF NOT EXISTS 'accepted';
ALTER TYPE submission_status ADD VALUE IF NOT EXISTS 'rejected';
ALTER TYPE validator_decision ADD VALUE IF NOT EXISTS 'approve';
ALTER TYPE validator_decision ADD VALUE IF NOT EXISTS 'reject';
ALTER TYPE earnings_role ADD VALUE IF NOT EXISTS 'contributor';
ALTER TYPE earnings_role ADD VALUE IF NOT EXISTS 'validator';
ALTER TYPE earnings_status ADD VALUE IF NOT EXISTS 'pending';
ALTER TYPE earnings_status ADD VALUE IF NOT EXISTS 'paid';
ALTER TYPE earnings_status ADD VALUE IF NOT EXISTS 'failed';
ALTER TYPE submission_kind ADD VALUE IF NOT EXISTS 'new_content';
ALTER TYPE submission_kind ADD VALUE IF NOT EXISTS 'correction';
ALTER TYPE submission_kind ADD VALUE IF NOT EXISTS 'dialect_variant';
ALTER TYPE submission_kind ADD VALUE IF NOT EXISTS 'audio';
ALTER TYPE age_band ADD VALUE IF NOT EXISTS 'child_u13';
ALTER TYPE age_band ADD VALUE IF NOT EXISTS 'young_adult_13_25';
ALTER TYPE age_band ADD VALUE IF NOT EXISTS 'adult_25_plus';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'complete_beginner';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'language_enthusiast';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'connected_to_igbo_family';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'igbo_heritage_speaker';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'igbo_parent_abroad';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'mixed_parent_abroad';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'aboriginal_native';
ALTER TYPE connection_type ADD VALUE IF NOT EXISTS 'other_african_heritage';
ALTER TYPE learning_goal ADD VALUE IF NOT EXISTS 'family_and_culture';
ALTER TYPE learning_goal ADD VALUE IF NOT EXISTS 'teach_my_children';
ALTER TYPE learning_goal ADD VALUE IF NOT EXISTS 'visiting_nigeria';
ALTER TYPE learning_goal ADD VALUE IF NOT EXISTS 'academic_professional';
ALTER TYPE learning_goal ADD VALUE IF NOT EXISTS 'cultural_pride';
ALTER TYPE learning_goal ADD VALUE IF NOT EXISTS 'new_language';
ALTER TYPE learning_goal ADD VALUE IF NOT EXISTS 'improve_proverbs_vocab';
ALTER TYPE learning_style ADD VALUE IF NOT EXISTS 'game_points';
ALTER TYPE learning_style ADD VALUE IF NOT EXISTS 'structured_lessons';
ALTER TYPE learning_style ADD VALUE IF NOT EXISTS 'mixed';
ALTER TYPE study_mode ADD VALUE IF NOT EXISTS 'flashcard';
ALTER TYPE study_mode ADD VALUE IF NOT EXISTS 'quiz';
ALTER TYPE study_mode ADD VALUE IF NOT EXISTS 'phrase_practice';
ALTER TYPE study_mode ADD VALUE IF NOT EXISTS 'proverbs';
ALTER TYPE flag_reason ADD VALUE IF NOT EXISTS 'bad_audio';
ALTER TYPE flag_reason ADD VALUE IF NOT EXISTS 'wrong_translation';
ALTER TYPE flag_reason ADD VALUE IF NOT EXISTS 'cultural_inaccuracy';
ALTER TYPE flag_reason ADD VALUE IF NOT EXISTS 'spelling_or_tone';
ALTER TYPE flag_reason ADD VALUE IF NOT EXISTS 'offensive';
ALTER TYPE flag_reason ADD VALUE IF NOT EXISTS 'other';
ALTER TYPE flag_status ADD VALUE IF NOT EXISTS 'open';
ALTER TYPE flag_status ADD VALUE IF NOT EXISTS 'in_review';
ALTER TYPE flag_status ADD VALUE IF NOT EXISTS 'resolved';
ALTER TYPE flag_status ADD VALUE IF NOT EXISTS 'rejected';
