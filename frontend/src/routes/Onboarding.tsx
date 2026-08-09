import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { QuizFeedback } from "../components/QuizFeedback";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import { defaultMetaLanguage } from "../lib/locale";
import type {
  CatalogueLanguage,
  ContentItem,
  ContentPage,
  Difficulty,
  LanguageCatalogue,
  UserProfile,
} from "../lib/types";
import { OptionList } from "../onboarding/OptionList";
import {
  ageChoices,
  connectionChoicesFor,
  dailyChoices,
  goalChoicesFor,
  styleChoices,
} from "../onboarding/options";

type PreferenceChanges = Record<string, string | number | boolean | null>;
type QuizQuestion = { item: ContentItem; options: string[] };

const headings = [
  "Nnọọ",
  "Choose your languages",
  "Who are you",
  "Your connection",
  "Your goal",
  "Learning style",
  "Daily time",
  "Reminder",
  "Placement check",
  "Ready to begin",
];

function quizQuestion(page: ContentPage): QuizQuestion | null {
  for (const item of page.items) {
    const distractors = page.items
      .filter(
        (candidate) =>
          candidate.id !== item.id &&
          candidate.content_type === item.content_type,
      )
      .map((candidate) => candidate.translation)
      .filter(
        (translation, index, values) => values.indexOf(translation) === index,
      )
      .slice(0, 3);
    if (distractors.length === 3)
      return { item, options: [item.translation, ...distractors] };
  }
  return null;
}

export function Onboarding() {
  const navigate = useNavigate();
  const { step: rawStep } = useParams();
  const step = Number(rawStep ?? 1);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [slow, setSlow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<(() => void) | null>(null);
  const [time, setTime] = useState("09:00");
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [correct, setCorrect] = useState(0);
  const [catalogue, setCatalogue] = useState<LanguageCatalogue | null>(null);
  const [revisitMessage, setRevisitMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void apiFetch<UserProfile>("/v1/me", {
      authenticated: true,
      onSlowChange: (value) => active && setSlow(value),
    })
      .then((value) => {
        if (!active) return;
        setProfile(value);
        if (value.preferences.reminder_time)
          setTime(value.preferences.reminder_time.slice(0, 5));
      })
      .catch(
        (caught: unknown) =>
          active &&
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to load onboarding",
          ),
      );
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if ((step !== 2 && step !== 10) || catalogue) return;
    let active = true;
    void apiFetch<LanguageCatalogue>("/v1/languages/catalogue", {
      onSlowChange: (value) => active && setSlow(value),
    })
      .then((value) => active && setCatalogue(value))
      .catch((caught: unknown) =>
        active &&
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to load the language catalogue",
        ),
      );
    return () => {
      active = false;
    };
  }, [catalogue, step]);

  useEffect(() => {
    if (step !== 9 || questions) return;
    const difficulties: Difficulty[] = ["beginner", "intermediate", "advanced"];
    void Promise.all(
      difficulties.map((difficulty) =>
        apiFetch<ContentPage>(
          `/v1/content?language=ibo&difficulty=${difficulty}&limit=50`,
          {
            onSlowChange: setSlow,
          },
        ),
      ),
    )
      .then((pages) => {
        const built = pages.map(quizQuestion);
        if (built.some((question) => question === null))
          throw new Error(
            "Placement questions are unavailable. You can skip this check.",
          );
        setQuestions(built as QuizQuestion[]);
      })
      .catch((caught: unknown) =>
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to load placement questions",
        ),
      );
  }, [questions, step]);

  const preferences = profile?.preferences;
  const timezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    [],
  );

  async function save(changes: PreferenceChanges, nextStep: number) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch<UserProfile>("/v1/me/preferences", {
        method: "PATCH",
        authenticated: true,
        body: JSON.stringify({ ...changes, onboarding_last_screen: nextStep }),
        onSlowChange: setSlow,
      });
      setProfile((current) =>
        current
          ? {
              ...current,
              preferences: {
                ...current.preferences,
                ...changes,
                onboarding_last_screen: nextStep,
              },
            }
          : current,
      );
      setRetry(null);
      navigate(`/onboarding/${nextStep}`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "We could not save your answer",
      );
      setRetry(() => () => void save(changes, nextStep));
    } finally {
      setBusy(false);
    }
  }

  async function skip() {
    setBusy(true);
    try {
      await apiFetch<UserProfile>("/v1/me/onboarding/skip", {
        method: "POST",
        authenticated: true,
        body: JSON.stringify({ onboarding_last_screen: step }),
        onSlowChange: setSlow,
      });
      navigate("/");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "We could not skip onboarding",
      );
      setRetry(() => () => void skip());
    } finally {
      setBusy(false);
    }
  }

  async function complete() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch<UserProfile>("/v1/me/onboarding/complete", {
        method: "POST",
        authenticated: true,
        onSlowChange: setSlow,
      });
      navigate("/");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "We could not finish onboarding",
      );
      setRetry(() => () => void complete());
    } finally {
      setBusy(false);
    }
  }

  if (!Number.isInteger(step) || step < 1 || step > 10)
    return <Navigate replace to="/onboarding/1" />;
  if (!profile)
    return (
      <Spinner
        label={slow ? "Waking the server…" : "Loading your journey"}
        fullScreen
      />
    );

  const optionScreen =
    step === 3 ? (
      <OptionList
        choices={ageChoices}
        selected={preferences?.age_band}
        disabled={busy}
        onSelect={(value) => {
          const goalIsValid = goalChoicesFor(
            value,
            preferences?.connection,
          ).some(({ value: goal }) => goal === preferences?.goal);
          if (preferences?.goal && !goalIsValid) {
            setRevisitMessage(
              "Your earlier goal no longer fits this answer. Please choose it again.",
            );
            void save({ age_band: value, goal: null }, 5);
          } else {
            void save({ age_band: value }, 4);
          }
        }}
      />
    ) : step === 4 ? (
      <OptionList
        choices={connectionChoicesFor(preferences?.age_band)}
        selected={preferences?.connection}
        disabled={busy}
        onSelect={(value) => {
          const goalIsValid = goalChoicesFor(
            preferences?.age_band,
            value,
          ).some(({ value: goal }) => goal === preferences?.goal);
          if (preferences?.goal && !goalIsValid) {
            setRevisitMessage(
              "Your earlier goal no longer fits this answer. Please choose it again.",
            );
            void save({ connection: value, goal: null }, 5);
          } else {
            void save({ connection: value }, 5);
          }
        }}
      />
    ) : step === 5 ? (
      <OptionList
        choices={goalChoicesFor(
          preferences?.age_band,
          preferences?.connection,
        )}
        selected={preferences?.goal}
        disabled={busy}
        onSelect={(value) => void save({ goal: value }, 6)}
      />
    ) : step === 6 ? (
      <OptionList
        choices={styleChoices}
        selected={preferences?.style}
        disabled={busy}
        onSelect={(value) => void save({ style: value }, 7)}
      />
    ) : step === 7 ? (
      <OptionList
        choices={dailyChoices}
        selected={preferences?.daily_minutes as 5 | 15 | 30 | null}
        disabled={busy}
        onSelect={(value) => void save({ daily_minutes: value }, 8)}
      />
    ) : null;

  const question = questions?.[questionIndex];

  return (
    <main className="min-h-dvh bg-warm px-5 py-6 text-ink">
      <div className="mx-auto max-w-md">
        <div className="mb-6 flex items-center justify-between gap-4">
          {step > 1 ? (
            <button
              className="min-h-11 px-2 font-semibold text-indigo-deep"
              onClick={() => navigate(`/onboarding/${step - 1}`)}
            >
              ← Back
            </button>
          ) : (
            <span />
          )}
          <button
            className="min-h-11 px-2 font-semibold text-terracotta"
            disabled={busy}
            onClick={() => void skip()}
          >
            Skip for now
          </button>
        </div>
        <div
          aria-label={`Step ${step} of 10`}
          className="mb-8 h-2 overflow-hidden rounded-full bg-sand"
        >
          <div
            className="h-full rounded-full bg-ochre transition-[width]"
            style={{ width: `${(step / 10) * 100}%` }}
          />
        </div>
        <section
          key={step}
          className="onboarding-screen rounded-[2rem] bg-cream p-6 shadow-card motion-reduce:animate-none"
        >
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-terracotta">
            Setting up · Step {step} of 10
          </p>
          <h1 className="mt-2 font-display text-3xl font-semibold text-indigo-deep">
            {headings[step - 1]}
          </h1>
          {step === 1 && (
            <p className="mt-4 leading-7 text-muted">
              Welcome. Let&apos;s personalise your journey.
            </p>
          )}
          <div className="mt-6">
            {step === 1 && (
              <Button busy={busy} onClick={() => void save({}, 2)}>
                Get started
              </Button>
            )}
            {step === 2 &&
              (catalogue ? (
                <LanguagePair
                  catalogue={catalogue}
                  activeLanguage={profile.preferences.active_language}
                  metaLanguage={
                    profile.preferences.meta_language ?? defaultMetaLanguage()
                  }
                  busy={busy}
                  onConfirm={(active_language, meta_language) =>
                    void save({ active_language, meta_language }, 3)
                  }
                />
              ) : !error ? (
                <Spinner
                  label={slow ? "Waking the server…" : "Loading languages"}
                />
              ) : null)}
            {optionScreen}
            {step === 5 && revisitMessage && (
              <p role="status" className="mb-4 text-sm text-terracotta">
                {revisitMessage}
              </p>
            )}
            {step === 8 && (
              <div className="space-y-4">
                <label className="grid gap-2 font-semibold text-indigo-deep">
                  Reminder time
                  <input
                    aria-label="Reminder time"
                    type="time"
                    value={time}
                    onChange={(event) => setTime(event.target.value)}
                    className="min-h-11 rounded-xl border border-sand bg-white px-3"
                  />
                </label>
                <Button
                  busy={busy}
                  onClick={() =>
                    void save(
                      {
                        reminder_enabled: true,
                        reminder_time: `${time}:00`,
                        timezone,
                      },
                      9,
                    )
                  }
                >
                  Set reminder
                </Button>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() =>
                    void save(
                      {
                        reminder_enabled: false,
                        reminder_time: null,
                        timezone,
                      },
                      9,
                    )
                  }
                >
                  No reminders
                </Button>
              </div>
            )}
            {step === 9 && (
              <div className="space-y-5">
                {question ? (
                  <>
                    <p className="text-sm font-semibold text-muted">
                      Question {questionIndex + 1} of 3
                    </p>
                    <p className="font-display text-2xl font-semibold text-indigo-deep">
                      {question.item.target_text}
                    </p>
                    <QuizFeedback
                      key={questionIndex}
                      choices={[
                        ...question.options.map((value) => ({
                          label: value,
                          isCorrect: value === question.item.translation,
                        })),
                        {
                          label: "I'm not sure",
                          isCorrect: false,
                          isNeutral: true,
                        },
                      ]}
                      disabled={busy}
                      onSelect={(answer) =>
                        setCorrect((value) => value + Number(answer.isCorrect))
                      }
                      onContinue={() => {
                        if (questionIndex < 2) {
                          setQuestionIndex((index) => index + 1);
                        } else {
                          const placement_level =
                            correct === 3
                              ? "advanced"
                              : correct === 2
                                ? "intermediate"
                                : "beginner";
                          void save({ placement_level }, 10);
                        }
                      }}
                    />
                  </>
                ) : !error ? (
                  <Spinner
                    label={
                      slow ? "Waking the server…" : "Preparing your questions"
                    }
                  />
                ) : null}
                <button
                  className="min-h-11 w-full font-semibold text-terracotta underline"
                  disabled={busy}
                  onClick={() => void save({}, 10)}
                >
                  Skip this
                </button>
              </div>
            )}
            {step === 10 && (
              <CompletionSummary
                catalogue={catalogue}
                profile={profile}
                busy={busy}
                onComplete={() => void complete()}
                onChange={() => navigate("/onboarding/3")}
              />
            )}
          </div>
          {slow && busy && (
            <p
              role="status"
              className="mt-4 text-center text-sm font-semibold text-muted"
            >
              Waking the server…
            </p>
          )}
          {error && (
            <div className="mt-4 space-y-3">
              <ErrorMessage message={error} />
              {retry && (
                <Button variant="secondary" onClick={retry}>
                  Retry
                </Button>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function languageLabel(language: CatalogueLanguage) {
  return language.endonym && language.endonym !== language.name
    ? `${language.name} · ${language.endonym}`
    : language.name;
}

function LanguagePair({
  catalogue,
  activeLanguage,
  metaLanguage,
  busy,
  onConfirm,
}: {
  catalogue: LanguageCatalogue;
  activeLanguage: string;
  metaLanguage: string;
  busy: boolean;
  onConfirm: (active: string, meta: string) => void;
}) {
  const [active, setActive] = useState(activeLanguage);
  const [meta, setMeta] = useState(metaLanguage);
  const selectedMeta = catalogue.meta.find(({ code }) => code === meta);
  return (
    <div className="space-y-6">
      <LanguageChoices
        title="What do you want to learn?"
        languages={catalogue.learnable}
        selected={active}
        onSelect={setActive}
      />
      <LanguageChoices
        title="What language do you want to learn with?"
        languages={catalogue.meta}
        selected={meta}
        showCoverage
        onSelect={setMeta}
      />
      {selectedMeta &&
        (selectedMeta.translated_count ?? 0) < (selectedMeta.total_count ?? 0) && (
        <p className="rounded-xl bg-ochre-soft p-3 text-sm text-indigo-deep">
          {selectedMeta.name} translations are still being written — you&apos;ll
          see English where {selectedMeta.name} isn&apos;t ready yet.
        </p>
      )}
      <Button
        busy={busy}
        disabled={!active || !meta}
        onClick={() => onConfirm(active, meta)}
      >
        Continue
      </Button>
    </div>
  );
}

function LanguageChoices({
  title,
  languages,
  selected,
  showCoverage = false,
  onSelect,
}: {
  title: string;
  languages: CatalogueLanguage[];
  selected: string;
  showCoverage?: boolean;
  onSelect: (code: string) => void;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="mb-2 font-semibold text-indigo-deep">{title}</legend>
      {languages.map((language) => (
        <button
          key={language.code}
          type="button"
          disabled={!language.available}
          aria-pressed={selected === language.code}
          onClick={() => onSelect(language.code)}
          className={`min-h-11 w-full rounded-2xl border-2 px-4 py-3 text-left ${selected === language.code ? "border-ochre bg-ochre-soft" : "border-sand bg-white"} disabled:cursor-not-allowed disabled:opacity-60`}
        >
          <span className="font-semibold">{languageLabel(language)}</span>
          {!language.available && (
            <span className="ml-2 text-sm">Coming soon</span>
          )}
          {showCoverage && (
            <small className="block text-muted">
              {language.translated_count ?? 0}/{language.total_count ?? 0}{" "}
              translated
            </small>
          )}
        </button>
      ))}
    </fieldset>
  );
}

function CompletionSummary({
  catalogue,
  profile,
  busy,
  onComplete,
  onChange,
}: {
  catalogue: LanguageCatalogue | null;
  profile: UserProfile;
  busy: boolean;
  onComplete: () => void;
  onChange: () => void;
}) {
  const { preferences } = profile;
  const learnable = catalogue?.learnable.find(
    ({ code }) => code === preferences.active_language,
  );
  const meta = catalogue?.meta.find(
    ({ code }) => code === preferences.meta_language,
  );
  const summary = [
    ["Language pair", `${learnable?.name ?? preferences.active_language} with ${meta?.name ?? preferences.meta_language ?? "English"}`],
    ["Connection", connectionChoicesFor(preferences.age_band).find(({ value }) => value === preferences.connection)?.label ?? "Not set"],
    ["Goal", goalChoicesFor(preferences.age_band, preferences.connection).find(({ value }) => value === preferences.goal)?.label ?? "Not set"],
    ["Daily time", preferences.daily_minutes ? `${preferences.daily_minutes} minutes` : "Not set"],
  ];
  return (
    <div className="space-y-5">
      <dl className="space-y-3">
        {summary.map(([label, value]) => (
          <div key={label}>
            <dt className="text-sm font-semibold text-muted">{label}</dt>
            <dd className="text-indigo-deep">{value}</dd>
          </div>
        ))}
      </dl>
      <Button busy={busy} onClick={onComplete}>Bịa — Start learning</Button>
      <Button variant="secondary" disabled={busy} onClick={onChange}>Change something</Button>
    </div>
  );
}
