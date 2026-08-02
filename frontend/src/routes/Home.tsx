import { useEffect, useState } from "react";

import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import type { ResolvedTrack, UserProfile } from "../lib/types";

export function Home() {
  const { signOut } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [resolvedTrack, setResolvedTrack] = useState<ResolvedTrack | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    let active = true;
    const onSlowChange = (value: boolean) => active && setSlow(value);
    void Promise.all([
      apiFetch<UserProfile>("/v1/me", { authenticated: true, onSlowChange }),
      apiFetch<ResolvedTrack>("/v1/me/track", {
        authenticated: true,
        onSlowChange,
      }),
    ])
      .then(([nextProfile, nextTrack]) => {
        if (!active) return;
        setProfile(nextProfile);
        setResolvedTrack(nextTrack);
      })
      .catch((caught: unknown) => {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : "We could not load your home screen",
          );
      });
    return () => {
      active = false;
    };
  }, []);

  if (!profile || !resolvedTrack) {
    return (
      <main className="min-h-dvh bg-warm px-5 py-10">
        {error ? (
          <div className="mx-auto max-w-md">
            <ErrorMessage message={error} />
          </div>
        ) : (
          <Spinner
            label={slow ? "Waking the server…" : "Loading your Igbo path"}
            fullScreen
          />
        )}
      </main>
    );
  }

  return (
    <main className="min-h-dvh bg-warm px-5 py-8 text-ink">
      <div className="mx-auto max-w-2xl space-y-6">
        <header className="flex items-center justify-between gap-4">
          <p className="font-display text-3xl font-bold text-indigo-deep">
            Jalɛ
          </p>
          <Button
            className="w-auto"
            variant="secondary"
            onClick={() => void signOut()}
          >
            Sign out
          </Button>
        </header>
        <section className="rounded-[2rem] bg-indigo-deep p-7 text-cream shadow-card">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-ochre-pale">
            Nnọọ
          </p>
          <h1 className="mt-3 font-display text-4xl font-semibold">
            {profile.display_name ?? "Igbo learner"}
          </h1>
          <p className="mt-4 text-sm text-lavender">
            Share slug:{" "}
            <span className="font-semibold text-cream">
              {profile.share_slug ?? "Not set"}
            </span>
          </p>
        </section>
        <section className="rounded-[2rem] bg-cream p-7 shadow-card">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-terracotta">
            Your learning path
          </p>
          <h2 className="mt-2 font-display text-3xl font-semibold text-indigo-deep">
            {resolvedTrack.track.name}
          </h2>
          {resolvedTrack.track.description && (
            <p className="mt-3 leading-7 text-muted">
              {resolvedTrack.track.description}
            </p>
          )}
          <ol className="mt-6 space-y-3">
            {(resolvedTrack.track.units ?? []).map((unit) => (
              <li
                key={unit.position}
                className="flex min-h-14 items-center gap-4 rounded-2xl border border-sand bg-white px-4 py-3"
              >
                <span className="grid size-9 shrink-0 place-content-center rounded-full bg-ochre-soft font-bold text-indigo-deep">
                  {unit.position}
                </span>
                <div>
                  <p className="font-display text-lg font-semibold text-indigo-deep">
                    {unit.title}
                  </p>
                  <p className="text-sm text-muted">
                    {unit.available} items available
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}
