import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import type { DueStudyItems, ResolvedTrack, UserStats } from "../lib/types";

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
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);
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
    ])
      .then(([track, stats, due]) => active && setData({ track, stats, due }))
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
  const { track: resolved, stats, due } = data;
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
