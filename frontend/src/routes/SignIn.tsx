import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";

export function SignIn() {
  const { user, signInWithEmail, signInWithPassword, signInWithGoogle } =
    useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { from?: string; message?: string } | null;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"magic" | "password">("magic");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(state?.message ?? null);
  const emailInput = useRef<HTMLInputElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);
  const focusTarget = useRef<"email" | "password" | null>(null);

  useEffect(() => {
    if (user) navigate(state?.from ?? "/", { replace: true });
  }, [navigate, state?.from, user]);

  useEffect(() => {
    if (mode !== "password" || !focusTarget.current) return;
    const input =
      focusTarget.current === "email"
        ? emailInput.current
        : passwordInput.current;
    input?.focus({ preventScroll: true });
    focusTarget.current = null;
  }, [mode]);

  async function sendMagicLink(event: FormEvent) {
    event.preventDefault();
    if (!navigator.onLine) {
      setError("Sign-in requires an internet connection.");
      return;
    }
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

  function showPasswordForm() {
    setError(null);
    setSent(false);
    focusTarget.current = email ? "password" : "email";
    setMode("password");
  }

  function showMagicLinkForm() {
    setError(null);
    setMode("magic");
  }

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    if (!navigator.onLine) {
      setError("Sign-in requires an internet connection.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signInWithPassword(email, password);
    } catch (caught) {
      if (
        caught instanceof Error &&
        caught.message.toLowerCase().includes("invalid login credentials")
      ) {
        setError("That email or password is not correct.");
      } else {
        setError(
          caught instanceof Error && caught.message
            ? caught.message
            : "We could not sign you in. Please try again.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  const googleEnabled = import.meta.env.VITE_GOOGLE_ENABLED === "true";

  async function continueWithGoogle() {
    if (!navigator.onLine) {
      setError("Sign-in requires an internet connection.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signInWithGoogle();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Google sign-in failed",
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
          {googleEnabled && (
            <>
              <Button type="button" busy={busy} onClick={continueWithGoogle}>
                Continue with Google
              </Button>
              <div className="flex items-center gap-3 text-xs uppercase tracking-widest text-muted">
                <span className="h-px flex-1 bg-sand" />
                or continue with email
                <span className="h-px flex-1 bg-sand" />
              </div>
            </>
          )}
          {mode === "password" ? (
            <form className="space-y-4" onSubmit={submitPassword}>
              <label className="block text-sm font-semibold" htmlFor="email">
                Email address
              </label>
              <input
                ref={emailInput}
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="min-h-11 w-full rounded-2xl border border-sand bg-white px-4 py-3 outline-none focus:border-ochre focus:ring-2 focus:ring-ochre-soft"
                placeholder="you@example.com"
              />
              <label className="block text-sm font-semibold" htmlFor="password">
                Password
              </label>
              <input
                ref={passwordInput}
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="min-h-11 w-full rounded-2xl border border-sand bg-white px-4 py-3 outline-none focus:border-ochre focus:ring-2 focus:ring-ochre-soft"
              />
              <Button
                type="submit"
                variant={googleEnabled ? "secondary" : "primary"}
                busy={busy}
              >
                Sign in
              </Button>
              <button
                type="button"
                className="flex min-h-11 w-full items-center justify-center text-sm font-semibold text-indigo-deep underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ochre"
                onClick={showMagicLinkForm}
              >
                Use a magic link instead
              </button>
            </form>
          ) : sent ? (
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
                ref={emailInput}
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="min-h-11 w-full rounded-2xl border border-sand bg-white px-4 py-3 outline-none focus:border-ochre focus:ring-2 focus:ring-ochre-soft"
                placeholder="you@example.com"
              />
              <Button
                type="submit"
                variant={googleEnabled ? "secondary" : "primary"}
                busy={busy}
              >
                Send magic link
              </Button>
            </form>
          )}
          {mode === "magic" && (
            <button
              type="button"
              className="flex min-h-11 w-full items-center justify-center text-sm font-semibold text-indigo-deep underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ochre"
              onClick={showPasswordForm}
            >
              Sign in with a password instead
            </button>
          )}
        </div>
      </section>
    </main>
  );
}
