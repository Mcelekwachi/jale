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

CREATE TYPE content_type    AS ENUM ('word', 'phrase', 'proverb', 'story');
CREATE TYPE difficulty_level AS ENUM ('beginner', 'intermediate', 'advanced', 'native');
CREATE TYPE content_status  AS ENUM ('draft', 'published', 'hidden');
CREATE TYPE audio_status    AS ENUM ('missing', 'placeholder', 'verified');

CREATE TYPE user_role       AS ENUM ('learner', 'contributor', 'admin');

CREATE TYPE age_band        AS ENUM ('child_u13', 'young_adult_13_25', 'adult_25_plus');
CREATE TYPE connection_type AS ENUM (
  'complete_beginner',       -- no African connection
  'language_enthusiast',
  'connected_to_igbo_family',
  'igbo_heritage_speaker',
  'igbo_parent_abroad',
  'mixed_parent_abroad',
  'aboriginal_native',
  'other_african_heritage'
);
CREATE TYPE learning_goal   AS ENUM (
  'family_and_culture', 'teach_my_children', 'visiting_nigeria',
  'academic_professional', 'cultural_pride', 'new_language',
  'improve_proverbs_vocab'
);
CREATE TYPE learning_style  AS ENUM ('game_points', 'structured_lessons', 'mixed');
CREATE TYPE study_mode      AS ENUM ('flashcard', 'quiz', 'phrase_practice', 'proverbs');

CREATE TYPE flag_reason     AS ENUM (
  'bad_audio', 'wrong_translation', 'cultural_inaccuracy',
  'spelling_or_tone', 'offensive', 'other'
);
CREATE TYPE flag_status     AS ENUM ('open', 'in_review', 'resolved', 'rejected');

-- ---------------------------------------------------------------------
-- 2. LANGUAGE LAYER
-- The whole multi-language promise lives here.
-- ---------------------------------------------------------------------

CREATE TABLE languages (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code          TEXT NOT NULL UNIQUE,          -- ISO 639-3: 'ibo', 'yor', 'hau'
  name          TEXT NOT NULL,                 -- 'Igbo'
  endonym       TEXT,                          -- 'Asụsụ Igbo'
  flag_emoji    TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT FALSE,-- available for use in the app
  is_learnable  BOOLEAN NOT NULL DEFAULT FALSE,
  is_meta       BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order    SMALLINT NOT NULL DEFAULT 100,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dialects (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  language_id   SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  code          TEXT NOT NULL,                 -- 'central'
  name          TEXT NOT NULL,                 -- 'Central Igbo'
  is_default    BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (language_id, code)
);
CREATE UNIQUE INDEX one_default_dialect_per_language
  ON dialects (language_id) WHERE is_default;

-- Categories are per-language so Yoruba can have its own taxonomy,
-- but a shared slug ('greetings') keeps cross-language UI code generic.
CREATE TABLE categories (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  language_id   SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  slug          TEXT NOT NULL,                 -- 'greetings', 'family', 'body', 'numbers'
  name          TEXT NOT NULL,                 -- 'Greetings & Courtesy'
  icon          TEXT,
  sort_order    SMALLINT NOT NULL DEFAULT 100,
  UNIQUE (language_id, slug)
);

-- ---------------------------------------------------------------------
-- 3. CONTENT
-- One table for words, phrases, proverbs and (Phase 2) stories.
-- NOTE: column is target_text, NOT igbo_text — see ARCHITECTURE.md.
-- ---------------------------------------------------------------------

CREATE TABLE content_items (
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

-- prevents accidental duplicates when seeding, e.g. "Ndewo" twice as a word
CREATE UNIQUE INDEX content_items_natural_uniq
  ON content_items (language_id, content_type, lower(target_text));

CREATE INDEX content_items_browse_idx
  ON content_items (language_id, content_type, difficulty_level, status);
CREATE INDEX content_items_category_idx ON content_items (category_id);
CREATE INDEX content_items_flagged_idx
  ON content_items (flag_count DESC) WHERE flag_count > 0;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
    CREATE INDEX content_items_search_idx
      ON content_items USING gin (target_text gin_trgm_ops);
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- 4. USERS
-- app_users.id mirrors Supabase auth.users.id. Auth stays in Supabase.
-- ---------------------------------------------------------------------

CREATE TABLE app_users (
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

ALTER TABLE content_items
  ADD CONSTRAINT content_items_contributor_fk
    FOREIGN KEY (contributor_id) REFERENCES app_users(id) ON DELETE SET NULL,
  ADD CONSTRAINT content_items_verifier_fk
    FOREIGN KEY (verified_by) REFERENCES app_users(id) ON DELETE SET NULL;

-- Translations are keyed by content and meta-language so adding an explanation
-- language does not duplicate the target-language content.
CREATE TABLE content_translations (
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

-- Which languages a contributor is trusted for (Phase 2 uses it, Phase 1
-- just needs the row to exist so permissions aren't a code change later).
CREATE TABLE contributor_permissions (
  user_id       UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  language_id   SMALLINT NOT NULL REFERENCES languages(id) ON DELETE CASCADE,
  can_verify    BOOLEAN NOT NULL DEFAULT FALSE,
  granted_by    UUID REFERENCES app_users(id),
  granted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, language_id)
);

-- ---------------------------------------------------------------------
-- 5. ONBOARDING / PREFERENCES
-- One row per user. Written once, editable forever from Settings.
-- Every answer is nullable because onboarding is skippable at any screen.
-- ---------------------------------------------------------------------

CREATE TABLE user_preferences (
  user_id             UUID PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  active_language_id  SMALLINT REFERENCES languages(id),
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

-- ---------------------------------------------------------------------
-- 6. CURRICULUM TRACKS
-- The persona -> curriculum mapping is DATA, not an if/else ladder.
-- Adding "Yoruba heritage speaker" later = 1 track + 1 rule + N units.
-- ---------------------------------------------------------------------

CREATE TABLE tracks (
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

-- First matching rule (lowest priority number) wins. NULL = wildcard.
CREATE TABLE track_rules (
  id            SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  track_id      SMALLINT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  priority      SMALLINT NOT NULL,
  match_age     age_band[],                    -- NULL = any
  match_connection connection_type[],
  match_goal    learning_goal[],
  match_style   learning_style[],
  UNIQUE (track_id, priority)
);

-- The ordered syllabus. Each unit is a content query, not a content list,
-- so newly added/verified items flow into existing tracks automatically.
CREATE TABLE track_units (
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

-- ---------------------------------------------------------------------
-- 7. PROGRESS, STREAKS
-- ---------------------------------------------------------------------

CREATE TABLE user_progress (
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
CREATE INDEX user_progress_due_idx ON user_progress (user_id, due_at);

-- Source of truth for the streak. One row per active day.
CREATE TABLE user_daily_activity (
  user_id         UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  activity_date   DATE NOT NULL,               -- in the user's local timezone
  items_reviewed  INTEGER NOT NULL DEFAULT 0,
  seconds_spent   INTEGER NOT NULL DEFAULT 0,
  xp              INTEGER NOT NULL DEFAULT 0,
  goal_met        BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (user_id, activity_date)
);

-- Denormalised for fast profile/share-page reads.
CREATE TABLE user_stats (
  user_id            UUID PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  current_streak     INTEGER NOT NULL DEFAULT 0,
  longest_streak     INTEGER NOT NULL DEFAULT 0,
  last_activity_date DATE,
  total_items_seen   INTEGER NOT NULL DEFAULT 0,
  total_mastered     INTEGER NOT NULL DEFAULT 0,
  total_xp           INTEGER NOT NULL DEFAULT 0,
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 8. FLAGS & MODERATION
-- ---------------------------------------------------------------------

CREATE TABLE content_flags (
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
-- one open flag per user per item and meta-language scope
CREATE UNIQUE INDEX one_open_flag_per_user
  ON content_flags (content_id, user_id, COALESCE(meta_language_id, 0))
  WHERE status IN ('open', 'in_review');

-- Audit trail for every edit an admin or contributor makes.
CREATE TABLE content_revisions (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content_id    BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
  changed_by    UUID REFERENCES app_users(id) ON DELETE SET NULL,
  change_note   TEXT,
  before_state  JSONB NOT NULL,
  after_state   JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 9. TRIGGERS
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER content_items_touch BEFORE UPDATE ON content_items
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER content_translations_touch BEFORE UPDATE ON content_translations
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER user_preferences_touch BEFORE UPDATE ON user_preferences
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

CREATE TRIGGER content_translations_require_proverb_note
  BEFORE INSERT OR UPDATE ON content_translations
  FOR EACH ROW EXECUTE FUNCTION require_proverb_translation_cultural_note();

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

CREATE TRIGGER content_flags_sync
  AFTER INSERT OR UPDATE OR DELETE ON content_flags
  FOR EACH ROW EXECUTE FUNCTION sync_flag_count();

-- ---------------------------------------------------------------------
-- 10. ADMIN VIEW — the flag review queue
-- ---------------------------------------------------------------------

CREATE VIEW admin_flag_queue AS
SELECT c.id            AS content_id,
       l.name          AS language,
       c.content_type,
       c.target_text,
       ml.code         AS meta_language,
       ct.translation,
       c.flag_count,
       ct.verified,
       min(f.created_at) AS oldest_flag_at,
       array_agg(DISTINCT f.reason) AS reasons
  FROM content_items c
  JOIN languages l ON l.id = c.language_id
  JOIN content_flags f ON f.content_id = c.id
  LEFT JOIN languages ml ON ml.id = f.meta_language_id
  LEFT JOIN content_translations ct
    ON ct.content_id = c.id AND ct.meta_language_id = f.meta_language_id
 WHERE f.status IN ('open','in_review')
 GROUP BY c.id, l.name, ml.code, ct.translation, ct.verified
 ORDER BY c.flag_count DESC, oldest_flag_at ASC;

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
