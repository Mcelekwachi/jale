import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import type {
  DueStudyItems,
  MetaLanguage,
  ResolvedTrack,
  UserProfile,
  UserStats,
} from "../lib/types";
import { answerQueue } from "../study/answerQueueService";

const modeNames = {
  flashcard: "Flashcards",
  quiz: "Quiz",
  phrase_practice: "Phrase practice",
  proverbs: "Proverbs",
};

export function Home() {
  const [data, setData] = useState<{
    track: ResolvedTrack;
    stats: UserStats;
    due: DueStudyItems;
    profile: UserProfile;
    languages: MetaLanguage[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
  const [pendingAnswers, setPendingAnswers] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [syncComplete, setSyncComplete] = useState(false);
  useEffect(() => {
    let active = true;
    const update = () =>
      void answerQueue.count().then((count) => active && setPendingAnswers(count));
    update();
    window.addEventListener("jale:answer-queue-changed", update);
    return () => {
      active = false;
      window.removeEventListener("jale:answer-queue-changed", update);
    };
  }, []);
  useEffect(() => {
    let active = true;
    const options = {
      authenticated: true,
      onSlowChange: (value: boolean) => active && setSlow(value),
    };
    void Promise.all([
      apiFetch<ResolvedTrack>("/v1/me/track", options),
      apiFetch<UserStats>("/v1/me/stats", options),
      apiFetch<DueStudyItems>("/v1/study/due", options),
      apiFetch<UserProfile>("/v1/me", options),
      apiFetch<MetaLanguage[]>("/v1/languages/meta", options),
    ])
      .then(
        ([track, stats, due, profile, languages]) =>
          active && setData({ track, stats, due, profile, languages }),
      )
      .catch(
        (caught: unknown) =>
          active &&
          setError(
            caught instanceof Error
              ? caught.message
              : "We could not load your home screen",
          ),
      );
    return () => {
      active = false;
    };
  }, []);
  if (!data)
    return error ? (
      <main className="p-5">
        <ErrorMessage message={error} />
      </main>
    ) : (
      <Spinner
        label={slow ? "Waking the server…" : "Loading your Igbo path"}
        fullScreen
      />
    );
  const { track: resolved, stats, due, profile, languages } = data;
  const metaCode = profile.preferences.meta_language ?? "eng";
  const metaName =
    languages.find(({ code }) => code === metaCode)?.name ?? metaCode;
  return (
    <main className="min-h-dvh bg-warm px-5 py-7 text-ink">
      <div className="mx-auto max-w-2xl space-y-6">
        <header className="flex items-center justify-between">
          <span className="font-display text-3xl font-bold text-indigo-deep">
            Jalẹ
          </span>
          <Link
            className="inline-flex min-h-11 items-center px-3 font-semibold text-indigo-deep"
            to="/settings"
          >
            Settings
          </Link>
        </header>
        <section className="rounded-[2rem] bg-indigo-deep p-6 text-cream shadow-card">
          {stats.current_streak === 0 ? (
            <h1 className="font-display text-3xl">Start your streak today</h1>
          ) : (
            <h1 className="font-display text-3xl">
              {stats.current_streak} day streak
            </h1>
          )}
          <p className="mt-2 text-lavender">
            {stats.today_goal_met
              ? "✓ Today's goal met"
              : "Keep going to meet today's goal"}
          </p>
        </section>
        {(pendingAnswers > 0 || syncComplete) && (
          <section className="flex min-h-14 items-center justify-between gap-4 rounded-2xl bg-ochre-soft px-5 text-indigo-deep">
            <span className="font-bold">
              {pendingAnswers > 0
                ? `${pendingAnswers} pending answer${pendingAnswers === 1 ? "" : "s"}`
                : "All answers synced"}
            </span>
            {pendingAnswers > 0 && (
              <button
                type="button"
                disabled={syncing || !navigator.onLine}
                className="min-h-11 font-bold underline disabled:opacity-50"
                onClick={() => {
                  setSyncing(true);
                  setSyncComplete(false);
                  void answerQueue
                    .flush()
                    .then(() => answerQueue.count())
                    .then((count) => {
                      setPendingAnswers(count);
                      setSyncComplete(count === 0);
                    })
                    .finally(() => setSyncing(false));
                }}
              >
                {syncing ? "Syncing…" : "Sync now"}
              </button>
            )}
          </section>
        )}
        {due.items.length > 0 && (
          <section className="flex min-h-14 items-center justify-between rounded-2xl bg-ochre-soft px-5 font-bold text-indigo-deep">
            Review due <span>{due.items.length}</span>
          </section>
        )}
        <section className="rounded-[2rem] bg-cream p-6 shadow-card">
          <p className="text-xs font-bold uppercase tracking-[.2em] text-terracotta">
            Your learning path
          </p>
          <h2 className="mt-2 font-display text-3xl text-indigo-deep">
            {resolved.track.name}
          </h2>
          <p className="mt-1 text-sm text-muted">
            Learning with {metaName}
          </p>
          <ol className="mt-6 space-y-3">
            {(resolved.track.units ?? []).map((unit) => (
              <li key={unit.position}>
                {unit.available > 0 ? (
                  <Link
                    to={`/study/${resolved.track.slug}/${unit.position}`}
                    className="flex min-h-16 items-center gap-4 rounded-2xl border border-sand bg-white p-4"
                  >
                    <span className="grid size-10 place-content-center rounded-full bg-ochre-soft font-bold">
                      {unit.position}
                    </span>
                    <span>
                      <strong className="font-display text-lg text-indigo-deep">
                        {unit.title}
                      </strong>
                      <small className="block text-muted">
                        {modeNames[unit.mode]} · {unit.available} ready
                      </small>
                    </span>
                  </Link>
                ) : (
                  <div
                    aria-disabled="true"
                    className="flex min-h-16 items-center gap-4 rounded-2xl border border-sand bg-white/50 p-4 text-muted"
                  >
                    <span className="grid size-10 place-content-center rounded-full bg-sand">
                      {unit.position}
                    </span>
                    <span>
                      <strong className="font-display text-lg">
                        {unit.title}
                      </strong>
                      <small className="block">
                        {modeNames[unit.mode]} · Content is being prepared
                      </small>
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}
