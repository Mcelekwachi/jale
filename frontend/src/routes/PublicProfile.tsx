import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { ApiError, apiFetch } from "../lib/api";
import type { PublicProfileSummary } from "../lib/types";

function joinedLabel(joinedMonth: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${joinedMonth}-01T00:00:00Z`));
}

export function PublicProfile() {
  const { shareSlug = "" } = useParams();
  const [profile, setProfile] = useState<PublicProfileSummary | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void apiFetch<PublicProfileSummary>(`/v1/profile/${encodeURIComponent(shareSlug)}`)
      .then((next) => active && setProfile(next))
      .catch((caught: unknown) => {
        if (!active) return;
        const status =
          caught instanceof ApiError
            ? caught.status
            : typeof caught === "object" && caught !== null && "status" in caught
              ? (caught as { status: unknown }).status
              : undefined;
        if (status === 404) setMissing(true);
        else setError(caught instanceof Error ? caught.message : "Could not load this profile");
      });
    return () => {
      active = false;
    };
  }, [shareSlug]);

  if (missing)
    return (
      <main className="grid min-h-dvh place-content-center bg-warm p-5 text-center">
        <section className="rounded-[2rem] bg-cream p-8 shadow-card">
          <h1 className="font-display text-3xl text-indigo-deep">This profile isn't available</h1>
          <p className="mt-3 text-muted">The link may be incorrect or the profile may no longer be public.</p>
          <Link to="/" className="mt-6 inline-flex min-h-11 items-center rounded-xl bg-indigo-deep px-5 font-bold text-cream">Visit Jalɛ</Link>
        </section>
      </main>
    );
  if (error)
    return <main className="p-5"><ErrorMessage message={error} /></main>;
  if (!profile) return <Spinner label="Loading public profile" fullScreen />;

  return (
    <main className="min-h-dvh bg-warm px-5 py-10 text-ink">
      <section className="mx-auto max-w-lg rounded-[2rem] bg-cream p-8 shadow-card">
        <p className="font-display text-2xl font-bold text-indigo-deep">Jalɛ</p>
        <h1 className="mt-8 font-display text-4xl text-indigo-deep">{profile.display_name || "Jalɛ learner"}</h1>
        <p className="mt-2 text-muted">
          Learning {profile.language_name}
          {profile.language_endonym ? ` (${profile.language_endonym})` : ""} · Joined {joinedLabel(profile.joined_month)}
        </p>
        <dl className="mt-8 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-ochre-soft p-4"><dt className="text-sm">Current</dt><dd className="mt-1 font-display text-2xl font-bold">{profile.current_streak} day current streak</dd></div>
          <div className="rounded-2xl bg-ochre-soft p-4"><dt className="text-sm">Personal best</dt><dd className="mt-1 font-display text-2xl font-bold">{profile.longest_streak} day longest streak</dd></div>
          <div className="rounded-2xl bg-ochre-soft p-4"><dt className="text-sm">Progress</dt><dd className="mt-1 font-display text-2xl font-bold">{profile.total_mastered} mastered</dd></div>
        </dl>
      </section>
    </main>
  );
}
