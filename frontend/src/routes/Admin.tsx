import {
  Component,
  useEffect,
  useState,
  type ErrorInfo,
  type PropsWithChildren,
  type ReactNode,
} from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { ApiError, apiFetch } from "../lib/api";
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

function isConflict(error: unknown): boolean {
  return (
    (error instanceof ApiError && error.status === 409) ||
    (typeof error === "object" &&
      error !== null &&
      "status" in error &&
      error.status === 409)
  );
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
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [bulkNotes, setBulkNotes] = useState<Record<number, string>>({});
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadQueue = () =>
    apiFetch<AdminFlagQueueItem[]>("/v1/admin/flags", {
      authenticated: true,
    });

  useEffect(() => {
    let active = true;
    void loadQueue()
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

  const removeFlag = (contentId: number, flagId: number) => {
    setQueue((current) => {
      if (current.status !== "loaded") return current;
      const items = current.items.flatMap((item) => {
        if (item.content_id !== contentId) return [item];
        const flags = item.flags.filter((flag) => flag.id !== flagId);
        if (flags.length === 0) return [];
        return [
          {
            ...item,
            flags,
            flag_count: flags.length,
            reasons: [...new Set(flags.map((flag) => flag.reason))],
          },
        ];
      });
      return { status: "loaded", items };
    });
  };

  const refreshAfterConflict = async () => {
    const items = await loadQueue();
    setQueue({ status: "loaded", items });
    setMessage("This flag was already resolved");
  };

  const updateFlag = async (
    contentId: number,
    flagId: number,
    status: "resolved" | "rejected",
  ) => {
    const resolutionNote = notes[flagId]?.trim() ?? "";
    setMessage(null);
    setActionError(null);
    if (status === "rejected" && !resolutionNote) {
      setActionError("A resolution note is required to reject a flag");
      return;
    }
    setPendingAction(`${status}-${flagId}`);
    try {
      await apiFetch(`/v1/admin/flags/${flagId}`, {
        authenticated: true,
        method: "PATCH",
        body: JSON.stringify({
          status,
          resolution_note: resolutionNote || null,
        }),
      });
      removeFlag(contentId, flagId);
      setMessage(status === "resolved" ? "Flag resolved" : "Flag rejected");
    } catch (error) {
      if (isConflict(error)) {
        await refreshAfterConflict();
      } else {
        setActionError(messageFrom(error, `Unable to ${status} the flag`));
      }
    } finally {
      setPendingAction(null);
    }
  };

  const resolveAll = async (contentId: number) => {
    setMessage(null);
    setActionError(null);
    setPendingAction(`all-${contentId}`);
    try {
      await apiFetch(`/v1/admin/content/${contentId}/flags/resolve`, {
        authenticated: true,
        method: "POST",
        body: JSON.stringify({
          resolution_note: bulkNotes[contentId]?.trim() || null,
        }),
      });
      setQueue((current) =>
        current.status === "loaded"
          ? {
              status: "loaded",
              items: current.items.filter(
                (item) => item.content_id !== contentId,
              ),
            }
          : current,
      );
      setMessage("All flags resolved");
    } catch (error) {
      if (isConflict(error)) {
        await refreshAfterConflict();
      } else {
        setActionError(messageFrom(error, "Unable to resolve all flags"));
      }
    } finally {
      setPendingAction(null);
    }
  };

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
        {message && (
          <p
            role="status"
            className="mt-4 rounded-xl bg-ochre-soft p-3 text-indigo-deep"
          >
            {message}
          </p>
        )}
        {actionError && (
          <p
            role="alert"
            className="mt-4 rounded-xl bg-terracotta-soft p-3 text-terracotta-dark"
          >
            {actionError}
          </p>
        )}
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
                <ul className="mt-5 grid list-none gap-3 p-0">
                  {item.flags.map((flag) => (
                    <li
                      key={flag.id}
                      className="rounded-xl border border-indigo-deep/10 p-4"
                    >
                      <p className="font-semibold text-indigo-deep">
                        {flag.reason.replaceAll("_", " ")}
                      </p>
                      {flag.note && (
                        <p className="mt-1 text-sm text-muted">{flag.note}</p>
                      )}
                      <label className="mt-3 block text-sm font-semibold text-indigo-deep">
                        Resolution note for flag {flag.id}
                        <textarea
                          className="mt-1 min-h-20 w-full rounded-xl border border-indigo-deep/20 bg-white p-3 font-normal"
                          value={notes[flag.id] ?? ""}
                          onChange={(event) =>
                            setNotes((current) => ({
                              ...current,
                              [flag.id]: event.target.value,
                            }))
                          }
                        />
                      </label>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          aria-label={`Resolve flag ${flag.id}`}
                          disabled={pendingAction !== null}
                          className="rounded-xl bg-indigo-deep px-4 py-2 font-semibold text-white disabled:opacity-50"
                          onClick={() =>
                            void updateFlag(
                              item.content_id,
                              flag.id,
                              "resolved",
                            )
                          }
                        >
                          Resolve
                        </button>
                        <button
                          type="button"
                          aria-label={`Reject flag ${flag.id}`}
                          disabled={pendingAction !== null}
                          className="rounded-xl border border-terracotta-dark px-4 py-2 font-semibold text-terracotta-dark disabled:opacity-50"
                          onClick={() =>
                            void updateFlag(
                              item.content_id,
                              flag.id,
                              "rejected",
                            )
                          }
                        >
                          Reject
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
                {item.flags.length > 1 && (
                  <div className="mt-5 border-t border-indigo-deep/10 pt-5">
                    <label className="block text-sm font-semibold text-indigo-deep">
                      Shared resolution note for {item.target_text}
                      <textarea
                        className="mt-1 min-h-20 w-full rounded-xl border border-indigo-deep/20 bg-white p-3 font-normal"
                        value={bulkNotes[item.content_id] ?? ""}
                        onChange={(event) =>
                          setBulkNotes((current) => ({
                            ...current,
                            [item.content_id]: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <button
                      type="button"
                      aria-label={`Resolve all flags for ${item.target_text}`}
                      disabled={pendingAction !== null}
                      className="mt-3 rounded-xl bg-indigo-deep px-4 py-2 font-semibold text-white disabled:opacity-50"
                      onClick={() => void resolveAll(item.content_id)}
                    >
                      Resolve all
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

export function AdminRoute({ children }: PropsWithChildren) {
  const [profile, setProfile] = useState<ProfileState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    void apiFetch<UserProfile>("/v1/me", { authenticated: true })
      .then(
        (value) => active && setProfile({ status: "loaded", profile: value }),
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
  return children ?? <FlagQueue />;
}
