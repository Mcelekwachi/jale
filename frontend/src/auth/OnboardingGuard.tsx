import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { useUiStrings } from "../i18n/useUiStrings";
import { apiFetch } from "../lib/api";
import type { UserProfile } from "../lib/types";

export function OnboardingGuard() {
  const strings = useUiStrings().shared;
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    let active = true;
    void apiFetch<UserProfile>("/v1/me", {
      authenticated: true,
      onSlowChange: (value) => active && setSlow(value),
    })
      .then((value) => active && setProfile(value))
      .catch(
        (caught: unknown) =>
          active &&
          setError(
            caught instanceof Error ? caught.message : strings.profileLoadError,
          ),
      );
    return () => {
      active = false;
    };
  }, [strings.profileLoadError]);

  if (error)
    return (
      <main className="p-5">
        <ErrorMessage message={error} />
      </main>
    );
  if (!profile)
    return (
      <Spinner
        label={slow ? strings.wakingServer : strings.loadingJourney}
        fullScreen
      />
    );
  if (profile.preferences.onboarding_status === "not_started") {
    return (
      <Navigate
        replace
        to={`/onboarding/${profile.preferences.onboarding_last_screen ?? 1}`}
      />
    );
  }
  return <Outlet />;
}
