import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import { setUiLanguage, useUiStrings } from "../i18n/useUiStrings";
import type {
  DueStudyItems,
  MetaLanguage,
  ResolvedTrack,
  UserProfile,
  UserStats,
} from "../lib/types";
import { answerQueue } from "../study/answerQueueService";

export function Home() {
  const strings = useUiStrings().home;
  const modeNames = {
    flashcard: strings.flashcards,
    quiz: strings.quiz,
    phrase_practice: strings.phrasePractice,
    proverbs: strings.proverbs,
  };
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
      .then(([track, stats, due, profile, languages]) => {
        if (!active) return;
        setUiLanguage(profile.preferences.meta_language);
        setData({ track, stats, due, profile, languages });
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
  }, []);
  if (!data)
    return error ? (
      <main className="p-5">
        <ErrorMessage message={error} />
      </main>
    ) : (
      <Spinner
        label={slow ? strings.wakingServer : strings.loadingPath}
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
            {strings.settings}
          </Link>
        </header>
        <section className="rounded-[2rem] bg-indigo-deep p-6 text-cream shadow-card">
          {stats.current_streak === 0 ? (
            <h1 className="font-display text-3xl">{strings.startStreak}</h1>
          ) : (
            <h1 className="font-display text-3xl">
              {stats.current_streak} {strings.dayStreak}
            </h1>
          )}
          <p className="mt-2 text-lavender">
            {stats.today_goal_met ? strings.goalMet : strings.keepGoing}
          </p>
          {profile.share_slug && (
            <button
              type="button"
              className="mt-5 min-h-11 rounded-xl bg-cream px-5 font-bold text-indigo-deep"
              onClick={() => {
                const url = `${window.location.origin}/u/${profile.share_slug}`;
                const shareData = {
                  title: strings.shareTitle,
                  text: `${profile.display_name || strings.learner} — ${strings.learningProgress}`,
                  url,
                };
                if (navigator.share) {
                  void navigator.share(shareData);
                } else {
                  void navigator.clipboard
                    .writeText(url)
                    .then(() => setShareMessage(strings.linkCopied));
                }
              }}
            >
              {strings.shareProgress}
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
                ? `${pendingAnswers} ${pendingAnswers === 1 ? strings.pendingAnswer : strings.pendingAnswers}`
                : strings.answersSynced}
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
                {syncing ? strings.syncing : strings.syncNow}
              </button>
            )}
          </section>
        )}
        {due.items.length > 0 && (
          <section
            id="review-due"
            className="flex min-h-14 items-center justify-between rounded-2xl bg-ochre-soft px-5 font-bold text-indigo-deep"
          >
            {strings.reviewDue} <span>{due.items.length}</span>
          </section>
        )}
        <section className="rounded-[2rem] bg-cream p-6 shadow-card">
          <p className="text-xs font-bold uppercase tracking-[.2em] text-terracotta">
            {strings.learningPath}
          </p>
          <h2 className="mt-2 font-display text-3xl text-indigo-deep">
            {resolved.track.name}
          </h2>
          <p className="mt-1 text-sm text-muted">
            {strings.learningWith} {metaName}
          </p>
          <section
            aria-label={strings.continueCta}
            className="mt-6 rounded-3xl bg-indigo-deep p-6 text-cream shadow-card"
          >
            {allUnitsComplete ? (
              <>
                <p className="text-xs font-bold uppercase tracking-[.2em] text-lavender">
                  {strings.pathComplete}
                </p>
                <h3 className="mt-2 font-display text-2xl">
                  {strings.keepFresh}
                </h3>
                {due.items.length > 0 ? (
                  <a
                    href="#review-due"
                    className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-cream px-5 font-bold text-indigo-deep"
                  >
                    {strings.reviewDue}
                  </a>
                ) : (
                  <p className="mt-4 text-lavender">{strings.nothingDue}</p>
                )}
              </>
            ) : nextUnit ? (
              <>
                <p className="text-xs font-bold uppercase tracking-[.2em] text-lavender">
                  {strings.continueCta}
                </p>
                <h3 className="mt-2 font-display text-3xl">{nextUnit.title}</h3>
                <p className="mt-1 text-lavender">{modeNames[nextUnit.mode]}</p>
                <Link
                  to={`/study/${resolved.track.slug}/${nextUnit.position}`}
                  aria-label={`${nextUnit.progress.done > 0 ? strings.continueCta : strings.start} ${nextUnit.title}`}
                  className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-cream px-5 font-bold text-indigo-deep"
                >
                  {nextUnit.progress.done > 0
                    ? strings.continueCta
                    : strings.start}
                </Link>
              </>
            ) : (
              <p className="text-lavender">{strings.noUnits}</p>
            )}
          </section>
          <section
            aria-label={strings.fullPath}
            className="mt-6 border-t border-sand pt-5 text-sm"
          >
            <h3 className="font-bold text-indigo-deep">{strings.fullPath}</h3>
            <ol className="mt-3 divide-y divide-sand">
              {units.map((unit) => (
                <li key={unit.position}>
                  <Link
                    to={`/study/${resolved.track.slug}/${unit.position}`}
                    className="flex min-h-12 items-center gap-3 py-3 text-indigo-deep"
                  >
                    <span className="w-6 shrink-0 font-bold text-terracotta">
                      {unit.position}
                    </span>
                    <strong>{unit.title}</strong>
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        </section>
      </div>
    </main>
  );
}
