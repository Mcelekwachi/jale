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
  const [shareMessage, setShareMessage] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const update = () =>
      void answerQueue
        .count()
        .then((count) => active && setPendingAnswers(count));
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
  const units = resolved.track.units ?? [];
  const nextUnit = units.find((unit) => !unit.completed);
  const allUnitsComplete = units.length > 0 && !nextUnit;
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
          {profile.share_slug && (
            <button
              type="button"
              className="mt-5 min-h-11 rounded-xl bg-cream px-5 font-bold text-indigo-deep"
              onClick={() => {
                const url = `${window.location.origin}/u/${profile.share_slug}`;
                const shareData = {
                  title: "My Jalɛ progress",
                  text: `${profile.display_name || "A Jalɛ learner"}'s learning progress`,
                  url,
                };
                if (navigator.share) {
                  void navigator.share(shareData);
                } else {
                  void navigator.clipboard
                    .writeText(url)
                    .then(() => setShareMessage("Profile link copied"));
                }
              }}
            >
              Share my progress
            </button>
          )}
          {shareMessage && (
            <p role="status" className="mt-3 text-sm text-lavender">
              {shareMessage}
            </p>
          )}
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
          <section
            id="review-due"
            className="flex min-h-14 items-center justify-between rounded-2xl bg-ochre-soft px-5 font-bold text-indigo-deep"
          >
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
          <p className="mt-1 text-sm text-muted">Learning with {metaName}</p>
          <section
            aria-label="Continue"
            className="mt-6 rounded-3xl bg-indigo-deep p-6 text-cream shadow-card"
          >
            {allUnitsComplete ? (
              <>
                <p className="text-xs font-bold uppercase tracking-[.2em] text-lavender">
                  Path complete
                </p>
                <h3 className="mt-2 font-display text-2xl">
                  Keep your learning fresh
                </h3>
                <a
                  href="#review-due"
                  className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-cream px-5 font-bold text-indigo-deep"
                >
                  Review due
                </a>
              </>
            ) : nextUnit ? (
              <>
                <p className="text-xs font-bold uppercase tracking-[.2em] text-lavender">
                  Continue
                </p>
                <h3 className="mt-2 font-display text-3xl">{nextUnit.title}</h3>
                <p className="mt-1 text-lavender">{modeNames[nextUnit.mode]}</p>
                {nextUnit.available > 0 ? (
                  <Link
                    to={`/study/${resolved.track.slug}/${nextUnit.position}`}
                    aria-label={`${nextUnit.progress.done > 0 ? "Continue" : "Start"} ${nextUnit.title}`}
                    className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-cream px-5 font-bold text-indigo-deep"
                  >
                    {nextUnit.progress.done > 0 ? "Continue" : "Start"}
                  </Link>
                ) : (
                  <p className="mt-4 text-sm text-lavender">
                    Content is being prepared
                  </p>
                )}
              </>
            ) : (
              <p className="text-lavender">No units are available yet.</p>
            )}
          </section>
          <section
            aria-label="Full learning path"
            className="mt-6 border-t border-sand pt-5 text-sm"
          >
            <h3 className="font-bold text-indigo-deep">Full learning path</h3>
            <ol className="mt-3 divide-y divide-sand">
              {units.map((unit) => (
                <li key={unit.position}>
                  {unit.available > 0 ? (
                    <Link
                      to={`/study/${resolved.track.slug}/${unit.position}`}
                      className="flex min-h-12 items-center gap-3 py-3 text-indigo-deep"
                    >
                      <span className="w-6 shrink-0 font-bold text-terracotta">
                        {unit.position}
                      </span>
                      <strong>{unit.title}</strong>
                    </Link>
                  ) : (
                    <div
                      aria-disabled="true"
                      className="flex min-h-12 items-center gap-3 py-3 text-muted"
                    >
                      <span className="w-6 shrink-0">{unit.position}</span>
                      <span>
                        <strong>{unit.title}</strong>
                        <small className="ml-2">
                          Content is being prepared
                        </small>
                      </span>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </section>
        </section>
      </div>
    </main>
  );
}
