import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import type {
  ContentItem,
  ContentPage,
  Difficulty,
  UserProfile,
} from "../lib/types";
import { OptionList } from "../onboarding/OptionList";
import {
  ageChoices,
  connectionChoices,
  dailyChoices,
  goalChoices,
  styleChoices,
} from "../onboarding/options";

type PreferenceChanges = Record<string, string | number | boolean | null>;
type QuizQuestion = { item: ContentItem; options: string[] };

const headings = [
  "Nnọọ",
  "Who are you",
  "Your connection",
  "Your goal",
  "Learning style",
  "Daily time",
  "Reminder",
  "Placement check",
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
    if (step !== 8 || questions) return;
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

  async function complete(changes?: PreferenceChanges) {
    setBusy(true);
    setError(null);
    try {
      if (changes) {
        await apiFetch<UserProfile>("/v1/me/preferences", {
          method: "PATCH",
          authenticated: true,
          body: JSON.stringify({ ...changes, onboarding_last_screen: 8 }),
          onSlowChange: setSlow,
        });
      }
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
      setRetry(() => () => void complete(changes));
    } finally {
      setBusy(false);
    }
  }

  if (!Number.isInteger(step) || step < 1 || step > 8)
    return <Navigate replace to="/onboarding/1" />;
  if (!profile)
    return (
      <Spinner
        label={slow ? "Waking the server…" : "Loading your journey"}
        fullScreen
      />
    );

  const optionScreen =
    step === 2 ? (
      <OptionList
        choices={ageChoices}
        selected={preferences?.age_band}
        disabled={busy}
        onSelect={(value) => void save({ age_band: value }, 3)}
      />
    ) : step === 3 ? (
      <OptionList
        choices={connectionChoices}
        selected={preferences?.connection}
        disabled={busy}
        onSelect={(value) => void save({ connection: value }, 4)}
      />
    ) : step === 4 ? (
      <OptionList
        choices={goalChoices}
        selected={preferences?.goal}
        disabled={busy}
        onSelect={(value) => void save({ goal: value }, 5)}
      />
    ) : step === 5 ? (
      <OptionList
        choices={styleChoices}
        selected={preferences?.style}
        disabled={busy}
        onSelect={(value) => void save({ style: value }, 6)}
      />
    ) : step === 6 ? (
      <OptionList
        choices={dailyChoices}
        selected={preferences?.daily_minutes as 5 | 15 | 30 | null}
        disabled={busy}
        onSelect={(value) => void save({ daily_minutes: value }, 7)}
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
          aria-label={`Step ${step} of 8`}
          className="mb-8 h-2 overflow-hidden rounded-full bg-sand"
        >
          <div
            className="h-full rounded-full bg-ochre transition-[width]"
            style={{ width: `${(step / 8) * 100}%` }}
          />
        </div>
        <section className="rounded-[2rem] bg-cream p-6 shadow-card">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-terracotta">
            Step {step} of 8
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
            {optionScreen}
            {step === 7 && (
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
                      8,
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
                      8,
                    )
                  }
                >
                  No reminders
                </Button>
              </div>
            )}
            {step === 8 && (
              <div className="space-y-5">
                {question ? (
                  <>
                    <p className="text-sm font-semibold text-muted">
                      Question {questionIndex + 1} of 3
                    </p>
                    <p className="font-display text-2xl font-semibold text-indigo-deep">
                      {question.item.target_text}
                    </p>
                    <OptionList
                      choices={question.options.map((value) => ({
                        label: value,
                        value,
                      }))}
                      disabled={busy}
                      onSelect={(answer) => {
                        const nextCorrect =
                          correct +
                          Number(answer === question.item.translation);
                        if (questionIndex < 2) {
                          setCorrect(nextCorrect);
                          setQuestionIndex((index) => index + 1);
                        } else {
                          const placement_level =
                            nextCorrect === 3
                              ? "advanced"
                              : nextCorrect === 2
                                ? "intermediate"
                                : "beginner";
                          void complete({ placement_level });
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
                  onClick={() => void complete()}
                >
                  Skip this
                </button>
              </div>
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
