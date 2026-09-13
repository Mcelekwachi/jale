import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { QuizFeedback } from "../components/QuizFeedback";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import { defaultMetaLanguage } from "../lib/locale";
import {
  getUiStrings,
  setUiLanguage,
  useUiStrings,
} from "../i18n/useUiStrings";
import { coverageLabel, hasIncompleteCoverage } from "../lib/languageCoverage";
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
  const ui = useUiStrings();
  const strings = ui.onboarding;
  const headings = [
    "Nnọọ",
    strings.chooseLanguages,
    strings.who,
    strings.connection,
    strings.goal,
    strings.style,
    strings.dailyTime,
    strings.reminder,
    strings.placement,
    strings.ready,
  ];
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
  };
  const localize = <T extends string | number>(
    choices: { label: string; value: T }[],
  ) =>
    choices.map((choice) => ({
      ...choice,
      label: choiceLabels[String(choice.value)] ?? choice.label,
    }));
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
        setUiLanguage(value.preferences.meta_language);
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
              : getUiStrings().onboarding.loadError,
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
      .catch(
        (caught: unknown) =>
          active &&
          setError(
            caught instanceof Error
              ? caught.message
              : getUiStrings().onboarding.catalogueError,
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
          throw new Error(getUiStrings().onboarding.placementUnavailable);
        setQuestions(built as QuizQuestion[]);
      })
      .catch((caught: unknown) =>
        setError(
          caught instanceof Error
            ? caught.message
            : getUiStrings().onboarding.placementError,
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
      if ("meta_language" in changes)
        setUiLanguage(String(changes.meta_language));
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
      setError(caught instanceof Error ? caught.message : strings.saveError);
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
      setError(caught instanceof Error ? caught.message : strings.skipError);
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
      setError(caught instanceof Error ? caught.message : strings.finishError);
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
        label={slow ? strings.wakingServer : strings.loadingJourney}
        fullScreen
      />
    );

  const optionScreen =
    step === 3 ? (
      <OptionList
        choices={localize(ageChoices)}
        selected={preferences?.age_band}
        disabled={busy}
        onSelect={(value) => {
          const goalIsValid = goalChoicesFor(
            value,
            preferences?.connection,
          ).some(({ value: goal }) => goal === preferences?.goal);
          if (preferences?.goal && !goalIsValid) {
            setRevisitMessage(strings.goalChanged);
            void save({ age_band: value, goal: null }, 5);
          } else {
            void save({ age_band: value }, 4);
          }
        }}
      />
    ) : step === 4 ? (
      <OptionList
        choices={localize(connectionChoicesFor(preferences?.age_band))}
        selected={preferences?.connection}
        disabled={busy}
        onSelect={(value) => {
          const goalIsValid = goalChoicesFor(preferences?.age_band, value).some(
            ({ value: goal }) => goal === preferences?.goal,
          );
          if (preferences?.goal && !goalIsValid) {
            setRevisitMessage(strings.goalChanged);
            void save({ connection: value, goal: null }, 5);
          } else {
            void save({ connection: value }, 5);
          }
        }}
      />
    ) : step === 5 ? (
      <OptionList
        choices={localize(
          goalChoicesFor(preferences?.age_band, preferences?.connection),
        )}
        selected={preferences?.goal}
        disabled={busy}
        onSelect={(value) => void save({ goal: value }, 6)}
      />
    ) : step === 6 ? (
      <OptionList
        choices={localize(styleChoices)}
        selected={preferences?.style}
        disabled={busy}
        onSelect={(value) => void save({ style: value }, 7)}
      />
    ) : step === 7 ? (
      <OptionList
        choices={localize(dailyChoices)}
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
              {strings.back}
            </button>
          ) : (
            <span />
          )}
          <button
            className="min-h-11 px-2 font-semibold text-terracotta"
            disabled={busy}
            onClick={() => void skip()}
          >
            {strings.skipForNow}
          </button>
        </div>
        <div
          aria-label={`${strings.step} ${step} ${strings.ofTen}`}
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
            {strings.settingUp} · {strings.step} {step} {strings.ofTen}
          </p>
          <h1 className="mt-2 font-display text-3xl font-semibold text-indigo-deep">
            {headings[step - 1]}
          </h1>
          {step === 1 && (
            <p className="mt-4 leading-7 text-muted">{strings.welcome}</p>
          )}
          <div className="mt-6">
            {step === 1 && (
              <Button busy={busy} onClick={() => void save({}, 2)}>
                {strings.getStarted}
              </Button>
            )}
            {step === 2 &&
              (catalogue ? (
                <LanguagePair
                  catalogue={catalogue}
                  activeLanguage={
                    (profile.preferences.onboarding_last_screen ?? 0) >= 3
                      ? profile.preferences.active_language
                      : ""
                  }
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
                  label={slow ? strings.wakingServer : strings.loadingLanguages}
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
                  {strings.reminderTime}
                  <input
                    aria-label={strings.reminderTime}
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
                  {strings.setReminder}
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
                  {strings.noReminders}
                </Button>
              </div>
            )}
            {step === 9 && (
              <div className="space-y-5">
                {question ? (
                  <>
                    <p className="text-sm font-semibold text-muted">
                      {strings.question} {questionIndex + 1} {strings.ofThree}
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
                          label: strings.notSure,
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
                      slow ? strings.wakingServer : strings.preparingQuestions
                    }
                  />
                ) : null}
                <button
                  className="min-h-11 w-full font-semibold text-terracotta underline"
                  disabled={busy}
                  onClick={() => void save({}, 10)}
                >
                  {strings.skipThis}
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
              {strings.wakingServer}
            </p>
          )}
          {error && (
            <div className="mt-4 space-y-3">
              <ErrorMessage message={error} />
              {retry && (
                <Button variant="secondary" onClick={retry}>
                  {strings.retry}
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
  const strings = useUiStrings().onboarding;
  const [active, setActive] = useState(activeLanguage);
  const [meta, setMeta] = useState(metaLanguage);
  const selectedMeta = catalogue.meta.find(({ code }) => code === meta);
  return (
    <div className="space-y-6">
      <LanguageSelect
        title={strings.learnWhat}
        languages={catalogue.learnable}
        selected={active}
        placeholder={strings.chooseLanguage}
        onSelect={setActive}
      />
      {active && (
        <div className="onboarding-screen motion-reduce:animate-none">
          <LanguageSelect
            title={strings.learnWith}
            languages={catalogue.meta}
            selected={meta}
            showCoverage
            onSelect={setMeta}
          />
        </div>
      )}
      {selectedMeta && active && hasIncompleteCoverage(selectedMeta) && (
        <p className="rounded-xl bg-ochre-soft p-3 text-sm text-indigo-deep">
          {selectedMeta.name} {strings.translationsPending} {selectedMeta.name}{" "}
          {strings.notReady}
        </p>
      )}
      <Button
        busy={busy}
        disabled={!active || !meta}
        onClick={() => onConfirm(active, meta)}
      >
        {strings.continue}
      </Button>
    </div>
  );
}

function LanguageSelect({
  title,
  languages,
  selected,
  placeholder,
  showCoverage = false,
  onSelect,
}: {
  title: string;
  languages: CatalogueLanguage[];
  selected: string;
  placeholder?: string;
  showCoverage?: boolean;
  onSelect: (code: string) => void;
}) {
  const strings = useUiStrings().onboarding;
  return (
    <label className="grid gap-2 font-semibold text-indigo-deep">
      {title}
      <select
        value={selected}
        onChange={(event) => onSelect(event.target.value)}
        className="min-h-11 w-full rounded-xl border border-sand bg-white px-3 text-ink"
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {languages.map((language) => {
          const coverage = showCoverage
            ? coverageLabel(language, strings.translated)
            : null;
          return (
            <option
              key={language.code}
              value={language.code}
              disabled={!language.available}
            >
              {languageLabel(language)}
              {!language.available ? ` — ${strings.comingSoon}` : ""}
              {coverage ? ` — ${coverage}` : ""}
            </option>
          );
        })}
      </select>
    </label>
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
  const ui = useUiStrings();
  const strings = ui.onboarding;
  const summaryChoiceLabels: Record<string, string> = {
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
  };
  const { preferences } = profile;
  const learnable = catalogue?.learnable.find(
    ({ code }) => code === preferences.active_language,
  );
  const meta = catalogue?.meta.find(
    ({ code }) => code === preferences.meta_language,
  );
  const connection = connectionChoicesFor(preferences.age_band).find(
    ({ value }) => value === preferences.connection,
  );
  const goal = goalChoicesFor(
    preferences.age_band,
    preferences.connection,
  ).find(({ value }) => value === preferences.goal);
  const summary = [
    [
      strings.languagePair,
      `${learnable?.name ?? preferences.active_language} ${strings.with} ${meta?.name ?? preferences.meta_language ?? strings.english}`,
    ],
    [
      strings.connection,
      summaryChoiceLabels[String(connection?.value)] ??
        connection?.label ??
        strings.notSet,
    ],
    [
      strings.goal,
      summaryChoiceLabels[String(goal?.value)] ?? goal?.label ?? strings.notSet,
    ],
    [
      strings.dailyTime,
      preferences.daily_minutes
        ? `${preferences.daily_minutes} ${strings.minutes}`
        : strings.notSet,
    ],
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
      <Button busy={busy} onClick={onComplete}>
        {strings.startLearning}
      </Button>
      <Button variant="secondary" disabled={busy} onClick={onChange}>
        {strings.changeSomething}
      </Button>
    </div>
  );
}
