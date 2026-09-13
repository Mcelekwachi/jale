import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import { defaultMetaLanguage } from "../lib/locale";
import { coverageLabel } from "../lib/languageCoverage";
import { setUiLanguage, useUiStrings } from "../i18n/useUiStrings";
import type { MetaLanguage, UserPreferences, UserProfile } from "../lib/types";
import { OptionList } from "../onboarding/OptionList";
import {
  ageChoices,
  connectionChoicesFor,
  dailyChoices,
  goalChoicesFor,
  placementChoices,
  styleChoices,
} from "../onboarding/options";

export function Settings() {
  const ui = useUiStrings();
  const strings = ui.settings;
  const choiceLabels: Record<string, string> = {
    child_u13: ui.choices.childUnder13,
    young_adult_13_25: ui.choices.youngAdult,
    adult_25_plus: ui.choices.adult,
    complete_beginner: ui.choices.completeBeginner,
    language_enthusiast: ui.choices.languageEnthusiast,
    connected_to_igbo_family: ui.choices.connectedFamily,
    igbo_heritage_speaker: ui.choices.heritageSpeaker,
    igbo_parent_abroad: ui.choices.parentAbroad,
    mixed_parent_abroad: ui.choices.mixedParent,
    aboriginal_native: ui.choices.nativeSpeaker,
    other_african_heritage: ui.choices.otherAfricanHeritage,
    family_and_culture: ui.choices.familyCulture,
    teach_my_children: ui.choices.teachChildren,
    visiting_nigeria: ui.choices.visitingNigeria,
    academic_professional: ui.choices.academic,
    cultural_pride: ui.choices.culturalPride,
    new_language: ui.choices.newLanguage,
    improve_proverbs_vocab: ui.choices.improveProverbs,
    game_points: ui.choices.games,
    structured_lessons: ui.choices.structured,
    mixed: ui.choices.mixed,
    5: ui.choices.fiveMinutes,
    15: ui.choices.fifteenMinutes,
    30: ui.choices.thirtyMinutes,
    beginner: ui.choices.beginner,
    intermediate: ui.choices.intermediate,
    advanced: ui.choices.advanced,
  };
  const localize = <T extends string | number>(
    choices: { label: string; value: T }[],
  ) =>
    choices.map((choice) => ({
      ...choice,
      label: choiceLabels[String(choice.value)] ?? choice.label,
    }));
  const { signOut } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [languages, setLanguages] = useState<MetaLanguage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const browserTimezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    [],
  );
  const [timezone, setTimezone] = useState(browserTimezone);

  useEffect(() => {
    let active = true;
    void Promise.all([
      apiFetch<UserProfile>("/v1/me", {
        authenticated: true,
        onSlowChange: (value) => active && setSlow(value),
      }),
      apiFetch<MetaLanguage[]>("/v1/languages/meta", {
        onSlowChange: (value) => active && setSlow(value),
      }),
    ])
      .then(([nextProfile, nextLanguages]) => {
        if (!active) return;
        setUiLanguage(nextProfile.preferences.meta_language);
        setProfile(nextProfile);
        setLanguages(nextLanguages);
        setTimezone(nextProfile.preferences.timezone || browserTimezone);
      })
      .catch(
        (caught: unknown) =>
          active &&
          setError(
            caught instanceof Error ? caught.message : strings.loadError,
          ),
      );
    return () => {
      active = false;
    };
  }, [browserTimezone, strings.loadError]);

  async function update(
    field: keyof UserPreferences,
    value: string | number | boolean | null,
  ) {
    setSaving(field);
    setError(null);
    try {
      await apiFetch<UserProfile>("/v1/me/preferences", {
        method: "PATCH",
        authenticated: true,
        body: JSON.stringify({ [field]: value }),
        onSlowChange: setSlow,
      });
      if (field === "meta_language") setUiLanguage(String(value));
      setProfile((current) =>
        current
          ? {
              ...current,
              preferences: { ...current.preferences, [field]: value },
            }
          : current,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : strings.saveError);
    } finally {
      setSaving(null);
    }
  }

  if (!profile)
    return error ? (
      <main className="p-5">
        <ErrorMessage message={error} />
      </main>
    ) : (
      <Spinner
        label={slow ? strings.wakingServer : strings.loading}
        fullScreen
      />
    );
  const preferences = profile.preferences;
  const selectedMeta = preferences.meta_language ?? defaultMetaLanguage();

  return (
    <main className="min-h-dvh bg-warm px-5 py-6 text-ink">
      <div className="mx-auto max-w-2xl space-y-6">
        <header className="flex items-center justify-between gap-4">
          <div>
            <Link
              to="/"
              className="inline-flex min-h-11 items-center font-semibold text-indigo-deep"
            >
              {strings.home}
            </Link>
            <h1 className="font-display text-4xl font-semibold text-indigo-deep">
              {strings.heading}
            </h1>
            <p className="mt-1 text-sm text-muted">{strings.preferences}</p>
          </div>
          <Button
            className="w-auto"
            variant="secondary"
            onClick={() => void signOut()}
          >
            {strings.signOut}
          </Button>
        </header>
        {slow && saving && (
          <p role="status" className="text-sm font-semibold text-muted">
            {strings.wakingServer}
          </p>
        )}
        {error && <ErrorMessage message={error} />}
        <SettingSection title={strings.who}>
          <OptionList
            choices={localize(ageChoices)}
            selected={preferences.age_band}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("age_band", value)}
          />
        </SettingSection>
        <SettingSection title={strings.connection}>
          <OptionList
            choices={localize(connectionChoicesFor(preferences.age_band))}
            selected={preferences.connection}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("connection", value)}
          />
        </SettingSection>
        <SettingSection title={strings.goal}>
          <OptionList
            choices={localize(
              goalChoicesFor(preferences.age_band, preferences.connection),
            )}
            selected={preferences.goal}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("goal", value)}
          />
        </SettingSection>
        <SettingSection title={strings.style}>
          <OptionList
            choices={localize(styleChoices)}
            selected={preferences.style}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("style", value)}
          />
        </SettingSection>
        <SettingSection title={strings.dailyTime}>
          <OptionList
            choices={localize(dailyChoices)}
            selected={preferences.daily_minutes as 5 | 15 | 30 | null}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("daily_minutes", value)}
          />
        </SettingSection>
        <SettingSection title={strings.placement}>
          <OptionList
            choices={localize([...placementChoices])}
            selected={
              preferences.placement_level as
                "beginner" | "intermediate" | "advanced" | null
            }
            disabled={Boolean(saving)}
            onSelect={(value) => void update("placement_level", value)}
          />
        </SettingSection>
        <SettingSection title={strings.explanationLanguage}>
          <OptionList
            choices={languages.map((language) => ({
              label: [
                language.name,
                coverageLabel(language, strings.translated),
              ]
                .filter(Boolean)
                .join(" — "),
              value: language.code,
            }))}
            selected={selectedMeta}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("meta_language", value)}
          />
          {preferences.meta_language === null && (
            <p className="mt-3 text-sm text-muted">{strings.browserLanguage}</p>
          )}
        </SettingSection>
        <SettingSection title={strings.reminder}>
          <div className="space-y-3">
            <label className="grid gap-2 font-semibold text-indigo-deep">
              {strings.reminderTime}
              <input
                type="time"
                value={(preferences.reminder_time ?? "09:00").slice(0, 5)}
                onChange={(event) =>
                  void update("reminder_time", `${event.target.value}:00`)
                }
                className="min-h-11 rounded-xl border border-sand bg-white px-3"
              />
            </label>
            <OptionList
              choices={[
                { label: strings.remindersOn, value: "on" },
                { label: strings.noReminders, value: "off" },
              ]}
              selected={preferences.reminder_enabled ? "on" : "off"}
              disabled={Boolean(saving)}
              onSelect={(value) =>
                void update("reminder_enabled", value === "on")
              }
            />
          </div>
        </SettingSection>
        <SettingSection title={strings.timezone}>
          <div className="space-y-3">
            <label className="grid gap-2 font-semibold text-indigo-deep">
              {strings.ianaTimezone}
              <input
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
                className="min-h-11 rounded-xl border border-sand bg-white px-3"
              />
            </label>
            <Button
              busy={saving === "timezone"}
              onClick={() => void update("timezone", timezone)}
            >
              {strings.saveTimezone}
            </Button>
          </div>
        </SettingSection>
      </div>
    </main>
  );
}

function SettingSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[2rem] bg-cream p-6 shadow-card">
      <h2 className="mb-4 font-display text-2xl font-semibold text-indigo-deep">
        {title}
      </h2>
      {children}
    </section>
  );
}
