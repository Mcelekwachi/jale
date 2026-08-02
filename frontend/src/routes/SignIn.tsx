import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";

function isGoogleUnavailable(error: unknown): boolean {
  return (
    error instanceof Error &&
    /provider.+(not enabled|unsupported)|unsupported provider/i.test(
      error.message,
    )
  );
}

export function SignIn() {
  const { user, signInWithEmail, signInWithGoogle } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { from?: string; message?: string } | null;
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(state?.message ?? null);

  useEffect(() => {
    if (user) navigate(state?.from ?? "/", { replace: true });
  }, [navigate, state?.from, user]);

  async function sendMagicLink(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signInWithEmail(email);
      setSent(true);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "We could not send the magic link",
      );
    } finally {
      setBusy(false);
    }
  }

  async function continueWithGoogle() {
    setBusy(true);
    setError(null);
    try {
      await signInWithGoogle();
    } catch (caught) {
      setError(
        isGoogleUnavailable(caught)
          ? "Google sign-in is not available yet"
          : caught instanceof Error
            ? caught.message
            : "Google sign-in failed",
      );
      setBusy(false);
    }
  }

  return (
    <main className="min-h-dvh bg-warm px-5 py-10 text-ink">
      <section className="mx-auto max-w-md overflow-hidden rounded-[2rem] bg-cream shadow-card">
        <div className="bg-indigo-deep px-7 py-9 text-cream">
          <p className="font-display text-5xl font-bold tracking-tight">Jalɛ</p>
          <p className="mt-3 max-w-xs text-lg text-lavender">
            Bịanụ. Your Igbo learning journey starts here.
          </p>
        </div>
        <div className="space-y-6 px-7 py-8">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-terracotta">
              Welcome
            </p>
            <h1 className="mt-2 font-display text-3xl font-semibold text-indigo-deep">
              Sign in to continue
            </h1>
          </div>
          {error && <ErrorMessage message={error} />}
          {sent ? (
            <div className="rounded-2xl bg-ochre-soft p-5">
              <h2 className="font-display text-xl font-semibold text-indigo-deep">
                Check your email
              </h2>
              <p className="mt-2 text-sm leading-6">
                We sent a secure sign-in link to {email}.
              </p>
            </div>
          ) : (
            <form className="space-y-4" onSubmit={sendMagicLink}>
              <label className="block text-sm font-semibold" htmlFor="email">
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="min-h-11 w-full rounded-2xl border border-sand bg-white px-4 py-3 outline-none focus:border-ochre focus:ring-2 focus:ring-ochre-soft"
                placeholder="you@example.com"
              />
              <Button type="submit" busy={busy}>
                Send magic link
              </Button>
            </form>
          )}
          <div className="flex items-center gap-3 text-xs uppercase tracking-widest text-muted">
            <span className="h-px flex-1 bg-sand" />
            or
            <span className="h-px flex-1 bg-sand" />
          </div>
          <Button
            type="button"
            variant="secondary"
            busy={busy}
            onClick={continueWithGoogle}
          >
            Continue with Google
          </Button>
        </div>
      </section>
    </main>
  );
}
