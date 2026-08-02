import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import { defaultMetaLanguage } from "../lib/locale";
import type { MetaLanguage, UserPreferences, UserProfile } from "../lib/types";
import { OptionList } from "../onboarding/OptionList";
import {
  ageChoices,
  connectionChoices,
  dailyChoices,
  goalChoices,
  placementChoices,
  styleChoices,
} from "../onboarding/options";

export function Settings() {
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
        setProfile(nextProfile);
        setLanguages(nextLanguages);
        setTimezone(nextProfile.preferences.timezone || browserTimezone);
      })
      .catch(
        (caught: unknown) =>
          active &&
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to load settings",
          ),
      );
    return () => {
      active = false;
    };
  }, [browserTimezone]);

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
      setProfile((current) =>
        current
          ? {
              ...current,
              preferences: { ...current.preferences, [field]: value },
            }
          : current,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to save this setting",
      );
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
        label={slow ? "Waking the server…" : "Loading settings"}
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
              ← Home
            </Link>
            <h1 className="font-display text-4xl font-semibold text-indigo-deep">
              Settings
            </h1>
          </div>
          <Button
            className="w-auto"
            variant="secondary"
            onClick={() => void signOut()}
          >
            Sign out
          </Button>
        </header>
        {slow && saving && (
          <p role="status" className="text-sm font-semibold text-muted">
            Waking the server…
          </p>
        )}
        {error && <ErrorMessage message={error} />}
        <SettingSection title="Who are you">
          <OptionList
            choices={ageChoices}
            selected={preferences.age_band}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("age_band", value)}
          />
        </SettingSection>
        <SettingSection title="Your connection">
          <OptionList
            choices={connectionChoices}
            selected={preferences.connection}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("connection", value)}
          />
        </SettingSection>
        <SettingSection title="Your goal">
          <OptionList
            choices={goalChoices}
            selected={preferences.goal}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("goal", value)}
          />
        </SettingSection>
        <SettingSection title="Learning style">
          <OptionList
            choices={styleChoices}
            selected={preferences.style}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("style", value)}
          />
        </SettingSection>
        <SettingSection title="Daily time">
          <OptionList
            choices={dailyChoices}
            selected={preferences.daily_minutes as 5 | 15 | 30 | null}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("daily_minutes", value)}
          />
        </SettingSection>
        <SettingSection title="Placement level">
          <OptionList
            choices={placementChoices}
            selected={
              preferences.placement_level as
                "beginner" | "intermediate" | "advanced" | null
            }
            disabled={Boolean(saving)}
            onSelect={(value) => void update("placement_level", value)}
          />
        </SettingSection>
        <SettingSection title="Explanation language">
          <OptionList
            choices={languages.map((language) => ({
              label: `${language.name} — ${language.translated_count}/${language.total_count} translated`,
              value: language.code,
            }))}
            selected={selectedMeta}
            disabled={Boolean(saving)}
            onSelect={(value) => void update("meta_language", value)}
          />
          {preferences.meta_language === null && (
            <p className="mt-3 text-sm text-muted">
              Following your browser language until you choose.
            </p>
          )}
        </SettingSection>
        <SettingSection title="Reminder">
          <div className="space-y-3">
            <label className="grid gap-2 font-semibold text-indigo-deep">
              Reminder time
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
                { label: "Reminders on", value: "on" },
                { label: "No reminders", value: "off" },
              ]}
              selected={preferences.reminder_enabled ? "on" : "off"}
              disabled={Boolean(saving)}
              onSelect={(value) =>
                void update("reminder_enabled", value === "on")
              }
            />
          </div>
        </SettingSection>
        <SettingSection title="Timezone">
          <div className="space-y-3">
            <label className="grid gap-2 font-semibold text-indigo-deep">
              IANA timezone
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
              Save timezone
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
