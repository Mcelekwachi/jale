import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { useUiStrings } from "../i18n/useUiStrings";
import { apiFetch } from "../lib/api";

/** Asked once, before anything else: is this person 16 or older? */
export function AgeGate() {
  const strings = useUiStrings().family;
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const [under, setUnder] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm(next: string) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/v1/me/age", { method: "POST", authenticated: true });
      navigate(next, { replace: true });
    } catch {
      setError(strings.ageError);
      setBusy(false);
    }
  }

  // Under 16 on their own: keep nothing. The account row created at sign-in
  // (with their email) is deleted, then they are signed out.
  async function removeAndSignOut() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/v1/me?confirm=true", {
        method: "DELETE",
        authenticated: true,
      });
      await signOut();
      navigate("/signin", { replace: true });
    } catch {
      setError(strings.ageError);
      setBusy(false);
    }
  }

  if (under)
    return (
      <main className="min-h-dvh bg-warm px-5 py-10 text-ink">
        <div className="mx-auto max-w-md space-y-5">
          <h1 className="font-display text-3xl font-bold text-indigo-deep">
            {strings.underTitle}
          </h1>
          <p>{strings.underBody}</p>
          {error && <ErrorMessage message={error} />}
          <Button busy={busy} onClick={() => void removeAndSignOut()}>
            {strings.underConfirm}
          </Button>
        </div>
      </main>
    );
  return (
    <main className="min-h-dvh bg-warm px-5 py-10 text-ink">
      <div className="mx-auto max-w-md space-y-5">
        <h1 className="font-display text-3xl font-bold text-indigo-deep">
          {strings.ageTitle}
        </h1>
        <p>{strings.ageIntro}</p>
        {error && <ErrorMessage message={error} />}
        <div className="space-y-3">
          <Button busy={busy} onClick={() => void confirm("/")}>
            {strings.ageAdult}
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => void confirm("/settings")}
          >
            {strings.ageParent}
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => setUnder(true)}
          >
            {strings.ageUnder}
          </Button>
        </div>
      </div>
    </main>
  );
}
