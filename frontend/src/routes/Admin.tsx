import {
  Component,
  useEffect,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import type { ContentType, UserProfile } from "../lib/types";

interface AdminFlag {
  id: number;
  reason: string;
  note: string | null;
  reporter_id: string | null;
  status: string;
  created_at: string;
  meta_language: string | null;
}

interface AdminFlagQueueItem {
  content_id: number;
  target_text: string;
  content_type: ContentType;
  translation: string | null;
  flag_count: number;
  oldest_flag_at: string;
  reasons: string[];
  reporter_count: number;
  flags: AdminFlag[];
}

type ProfileState =
  | { status: "loading" }
  | { status: "loaded"; profile: UserProfile }
  | { status: "error"; message: string };

type QueueState =
  | { status: "loading" }
  | { status: "loaded"; items: AdminFlagQueueItem[] }
  | { status: "error"; message: string };

interface AdminErrorBoundaryProps {
  children: ReactNode;
}

interface AdminErrorBoundaryState {
  error: Error | null;
}

export class AdminErrorBoundary extends Component<
  AdminErrorBoundaryProps,
  AdminErrorBoundaryState
> {
  state: AdminErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): AdminErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Admin route render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="grid min-h-dvh place-content-center bg-warm p-5">
          <section
            role="alert"
            className="max-w-lg rounded-3xl bg-cream p-8 shadow-card"
          >
            <h1 className="font-display text-2xl text-indigo-deep">
              The admin page hit an error
            </h1>
            <p className="mt-3 text-muted">
              {this.state.error.message ||
                "The admin tools could not be displayed."}
            </p>
            <button
              className="mt-6 rounded-xl bg-indigo-deep px-4 py-3 font-semibold text-white"
              type="button"
              onClick={() => window.location.reload()}
            >
              Reload admin page
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function messageFrom(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function NoAdminAccess() {
  return (
    <main className="grid min-h-dvh place-content-center bg-warm p-5">
      <section className="max-w-lg rounded-3xl bg-cream p-8 text-center shadow-card">
        <h1 className="font-display text-2xl text-indigo-deep">
          No admin access
        </h1>
        <p className="mt-3 text-muted">
          Your account does not have permission to view the admin tools.
        </p>
      </section>
    </main>
  );
}

function FlagQueue() {
  const [queue, setQueue] = useState<QueueState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    void apiFetch<AdminFlagQueueItem[]>("/v1/admin/flags", {
      authenticated: true,
    })
      .then((items) => active && setQueue({ status: "loaded", items }))
      .catch(
        (error: unknown) =>
          active &&
          setQueue({
            status: "error",
            message: messageFrom(error, "Unable to load the flag queue"),
          }),
      );
    return () => {
      active = false;
    };
  }, []);

  if (queue.status === "loading") {
    return <Spinner label="Loading flag queue" fullScreen />;
  }
  if (queue.status === "error") {
    return (
      <main className="p-5">
        <ErrorMessage message={queue.message} />
      </main>
    );
  }

  return (
    <main className="min-h-dvh bg-warm p-5 sm:p-8">
      <div className="mx-auto max-w-5xl">
        <h1 className="font-display text-3xl text-indigo-deep">Flag queue</h1>
        {queue.items.length === 0 ? (
          <p className="mt-6 rounded-2xl bg-cream p-6 text-muted shadow-card">
            There are no open flags.
          </p>
        ) : (
          <ul className="mt-6 grid list-none gap-4 p-0">
            {queue.items.map((item) => (
              <li
                key={item.content_id}
                className="rounded-2xl bg-cream p-6 shadow-card"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="font-display text-xl text-indigo-deep">
                      {item.target_text}
                    </h2>
                    {item.translation && (
                      <p className="mt-1 text-muted">{item.translation}</p>
                    )}
                  </div>
                  <span className="rounded-full bg-ochre-soft px-3 py-1 text-sm font-semibold text-indigo-deep">
                    {item.flag_count} {item.flag_count === 1 ? "flag" : "flags"}
                  </span>
                </div>
                <ul className="mt-4 flex list-none flex-wrap gap-2 p-0">
                  {item.reasons.map((reason) => (
                    <li
                      key={reason}
                      className="rounded-full bg-terracotta-soft px-3 py-1 text-sm text-terracotta-dark"
                    >
                      {reason.replaceAll("_", " ")}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

export function AdminRoute() {
  const [profile, setProfile] = useState<ProfileState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    void apiFetch<UserProfile>("/v1/me", { authenticated: true })
      .then((value) =>
        active && setProfile({ status: "loaded", profile: value }),
      )
      .catch(
        (error: unknown) =>
          active &&
          setProfile({
            status: "error",
            message: messageFrom(error, "Unable to load your profile"),
          }),
      );
    return () => {
      active = false;
    };
  }, []);

  if (profile.status === "loading") {
    return <Spinner label="Loading admin profile" fullScreen />;
  }
  if (profile.status === "error") {
    return (
      <main className="p-5">
        <ErrorMessage message={profile.message} />
      </main>
    );
  }
  if (profile.profile.role !== "admin") return <NoAdminAccess />;
  return <FlagQueue />;
}
