import type { AgeBand, Connection, Goal, LearningStyle } from "../lib/types";

export interface Choice<T extends string | number> {
  label: string;
  value: T;
}

export const ageChoices: Choice<AgeBand>[] = [
  { label: "Child under 13 (a parent sets this up)", value: "child_u13" },
  { label: "Young adult 13-25", value: "young_adult_13_25" },
  { label: "Adult 25+", value: "adult_25_plus" },
];

export const connectionChoices: Choice<Connection>[] = [
  {
    label: "Complete beginner, no African connection",
    value: "complete_beginner",
  },
  { label: "Language enthusiast", value: "language_enthusiast" },
  { label: "Connected to an Igbo family", value: "connected_to_igbo_family" },
  { label: "Igbo heritage speaker", value: "igbo_heritage_speaker" },
  { label: "Igbo parent born abroad", value: "igbo_parent_abroad" },
  { label: "Mixed parent born abroad", value: "mixed_parent_abroad" },
  { label: "Native Igbo speaker", value: "aboriginal_native" },
  { label: "Other African heritage", value: "other_african_heritage" },
];

export const goalChoices: Choice<Goal>[] = [
  { label: "Connect with family and culture", value: "family_and_culture" },
  { label: "Teach my children", value: "teach_my_children" },
  { label: "Visiting Nigeria", value: "visiting_nigeria" },
  {
    label: "Academic or professional interest",
    value: "academic_professional",
  },
  { label: "Cultural pride and identity", value: "cultural_pride" },
  { label: "Learning a new language", value: "new_language" },
  {
    label: "Improve my proverbs and vocabulary",
    value: "improve_proverbs_vocab",
  },
];

export const styleChoices: Choice<LearningStyle>[] = [
  { label: "Games and points", value: "game_points" },
  { label: "Clean structured lessons", value: "structured_lessons" },
  { label: "A mix of both", value: "mixed" },
];

export const dailyChoices: Choice<5 | 15 | 30>[] = [
  { label: "5 minutes", value: 5 },
  { label: "15 minutes", value: 15 },
  { label: "30 minutes", value: 30 },
];

export const placementChoices = [
  { label: "Beginner", value: "beginner" },
  { label: "Intermediate", value: "intermediate" },
  { label: "Advanced", value: "advanced" },
] as const;
