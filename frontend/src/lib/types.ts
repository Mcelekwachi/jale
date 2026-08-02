export type ContentType = "word" | "phrase" | "proverb" | "story";
export type Difficulty = "beginner" | "intermediate" | "advanced" | "native";
export type StudyMode = "flashcard" | "quiz" | "phrase_practice" | "proverbs";
export type AgeBand = "child_u13" | "young_adult_13_25" | "adult_25_plus";
export type Connection =
  | "complete_beginner"
  | "language_enthusiast"
  | "connected_to_igbo_family"
  | "igbo_heritage_speaker"
  | "igbo_parent_abroad"
  | "mixed_parent_abroad"
  | "aboriginal_native"
  | "other_african_heritage";
export type Goal =
  | "family_and_culture"
  | "teach_my_children"
  | "visiting_nigeria"
  | "academic_professional"
  | "cultural_pride"
  | "new_language"
  | "improve_proverbs_vocab";
export type LearningStyle = "game_points" | "structured_lessons" | "mixed";

export interface ContentItem {
  id: number;
  source_key: string;
  language: string;
  content_type: ContentType;
  difficulty: Difficulty;
  category?: string | null;
  target_text: string;
  target_text_toned?: string | null;
  translation: string;
  meta_language: string;
  meta_language_used: string;
  literal_translation?: string | null;
  cultural_note?: string | null;
  example_sentence?: string | null;
  example_translation?: string | null;
  audio_url?: string | null;
  audio_state: string;
  verified: boolean;
  flag_count: number;
}

export interface QuizOption {
  text: string;
  is_correct: boolean;
}

export interface StudyItem {
  id: number;
  content_type: ContentType;
  prompt: string;
  answer: string;
  meta_language: string;
  meta_language_used: string;
  audio_url?: string | null;
  audio_state: string;
  target_text_toned?: string | null;
  literal_translation?: string | null;
  cultural_note?: string | null;
  example_sentence?: string | null;
  example_translation?: string | null;
  options?: QuizOption[] | null;
  verified: boolean;
  flag_count: number;
}

export interface StudySession {
  track: string;
  unit_position: number;
  unit_title: string;
  mode: StudyMode;
  items: StudyItem[];
}

export interface TrackUnit {
  position: number;
  title: string;
  mode: StudyMode;
  category?: string | null;
  content_type?: ContentType | null;
  difficulty?: Difficulty | null;
  item_count: number;
  available: number;
}

export interface Track {
  slug: string;
  name: string;
  description?: string | null;
  min_difficulty: Difficulty;
  max_difficulty: Difficulty;
  is_default: boolean;
  units?: TrackUnit[];
}

export interface ResolvedTrack {
  track: Track;
  matched_priority?: number | null;
  is_fallback: boolean;
}

export interface UserPreferences {
  active_language: string;
  meta_language?: string | null;
  active_dialect_id?: number | null;
  age_band?: AgeBand | null;
  connection?: Connection | null;
  goal?: Goal | null;
  style?: LearningStyle | null;
  daily_minutes?: number | null;
  reminder_enabled: boolean;
  reminder_time?: string | null;
  timezone: string;
  placement_level?: Difficulty | null;
  placement_skipped: boolean;
  onboarding_status: string;
  onboarding_last_screen?: number | null;
  completed_at?: string | null;
  updated_at: string;
}

export interface ContentPage {
  items: ContentItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface UserProfile {
  id: string;
  email?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  role: string;
  share_slug?: string | null;
  is_active: boolean;
  created_at: string;
  last_seen_at?: string | null;
  preferences: UserPreferences;
}

export interface MetaLanguage {
  code: string;
  name: string;
  endonym?: string | null;
  flag_emoji?: string | null;
  is_active: boolean;
  translated_count: number;
  total_count: number;
}
