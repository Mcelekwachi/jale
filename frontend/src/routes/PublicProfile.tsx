import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { ApiError, apiFetch } from "../lib/api";
import type { PublicProfileSummary } from "../lib/types";
import { useUiLanguage, useUiStrings } from "../i18n/useUiStrings";

function joinedLabel(joinedMonth: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${joinedMonth}-01T00:00:00Z`));
}

export function PublicProfile() {
  const strings = useUiStrings().publicProfile;
  const locale = useUiLanguage() === "nld" ? "nl" : "en";
  const { shareSlug = "" } = useParams();
  const [profile, setProfile] = useState<PublicProfileSummary | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void apiFetch<PublicProfileSummary>(
      `/v1/profile/${encodeURIComponent(shareSlug)}`,
    )
      .then((next) => active && setProfile(next))
      .catch((caught: unknown) => {
        if (!active) return;
        const status =
          caught instanceof ApiError
            ? caught.status
            : typeof caught === "object" &&
                caught !== null &&
                "status" in caught
              ? (caught as { status: unknown }).status
              : undefined;
        if (status === 404) setMissing(true);
        else
          setError(
            caught instanceof Error ? caught.message : strings.loadError,
          );
      });
    return () => {
      active = false;
    };
  }, [shareSlug, strings.loadError]);

  if (missing)
    return (
      <main className="grid min-h-dvh place-content-center bg-warm p-5 text-center">
        <section className="rounded-[2rem] bg-cream p-8 shadow-card">
          <h1 className="font-display text-3xl text-indigo-deep">
            {strings.unavailable}
          </h1>
          <p className="mt-3 text-muted">{strings.badLink}</p>
          <Link
            to="/"
            className="mt-6 inline-flex min-h-11 items-center rounded-xl bg-indigo-deep px-5 font-bold text-cream"
          >
            {strings.visit}
          </Link>
        </section>
      </main>
    );
  if (error)
    return (
      <main className="p-5">
        <ErrorMessage message={error} />
      </main>
    );
  if (!profile) return <Spinner label={strings.loading} fullScreen />;

  return (
    <main className="min-h-dvh bg-warm px-5 py-10 text-ink">
      <section className="mx-auto max-w-lg rounded-[2rem] bg-cream p-8 shadow-card">
        <p className="font-display text-2xl font-bold text-indigo-deep">Jalɛ</p>
        <h1 className="mt-8 font-display text-4xl text-indigo-deep">
          {profile.display_name || strings.learner}
        </h1>
        <p className="mt-2 text-muted">
          {strings.learning} {profile.language_name}
          {profile.language_endonym
            ? ` (${profile.language_endonym})`
            : ""} · {strings.joined} {joinedLabel(profile.joined_month, locale)}
        </p>
        <dl className="mt-8 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-ochre-soft p-4">
            <dt className="text-sm">{strings.current}</dt>
            <dd className="mt-1 font-display text-2xl font-bold">
              {profile.current_streak} {strings.currentStreak}
            </dd>
          </div>
          <div className="rounded-2xl bg-ochre-soft p-4">
            <dt className="text-sm">{strings.personalBest}</dt>
            <dd className="mt-1 font-display text-2xl font-bold">
              {profile.longest_streak} {strings.longestStreak}
            </dd>
          </div>
          <div className="rounded-2xl bg-ochre-soft p-4">
            <dt className="text-sm">{strings.progress}</dt>
            <dd className="mt-1 font-display text-2xl font-bold">
              {profile.total_mastered} {strings.mastered}
            </dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
