import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import type { AdminContentDetail, AdminContentPage } from "../lib/types";

type LoadState<T> =
  | { status: "loading" }
  | { status: "loaded"; value: T }
  | { status: "error"; message: string };

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function AdminContentList() {
  const [page, setPage] = useState<LoadState<AdminContentPage>>({
    status: "loading",
  });

  useEffect(() => {
    let active = true;
    void apiFetch<AdminContentPage>("/v1/admin/content", {
      authenticated: true,
    })
      .then((value) => active && setPage({ status: "loaded", value }))
      .catch(
        (error: unknown) =>
          active &&
          setPage({
            status: "error",
            message: errorMessage(error, "Unable to load content"),
          }),
      );
    return () => {
      active = false;
    };
  }, []);

  if (page.status === "loading")
    return <Spinner label="Loading admin content" fullScreen />;
  if (page.status === "error")
    return <ErrorMessage message={page.message} />;

  return (
    <main className="min-h-dvh bg-warm p-5 sm:p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="font-display text-3xl text-indigo-deep">
          Content management
        </h1>
        {page.value.items.length === 0 ? (
          <p className="mt-6 rounded-2xl bg-cream p-6 text-muted shadow-card">
            No content matches these filters.
          </p>
        ) : (
          <ul className="mt-6 list-none p-0">
            {page.value.items.map((item) => (
              <li key={item.id}>
                <Link to={`/admin/content/${item.id}`}>{item.target_text}</Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}

export function AdminContentDetailRoute() {
  const { contentId } = useParams();
  const [detail, setDetail] = useState<LoadState<AdminContentDetail>>({
    status: "loading",
  });

  useEffect(() => {
    let active = true;
    void apiFetch<AdminContentDetail>(`/v1/admin/content/${contentId}`, {
      authenticated: true,
    })
      .then((value) => active && setDetail({ status: "loaded", value }))
      .catch(
        (error: unknown) =>
          active &&
          setDetail({
            status: "error",
            message: errorMessage(error, "Unable to load content detail"),
          }),
      );
    return () => {
      active = false;
    };
  }, [contentId]);

  if (detail.status === "loading")
    return <Spinner label="Loading content detail" fullScreen />;
  if (detail.status === "error")
    return <ErrorMessage message={detail.message} />;

  return (
    <main className="min-h-dvh bg-warm p-5 sm:p-8">
      <div className="mx-auto max-w-5xl">
        <Link className="text-indigo-rich underline" to="/admin/content">
          Back to content
        </Link>
        <h1 className="mt-4 font-display text-3xl text-indigo-deep">
          Edit content
        </h1>
        <p className="mt-2 font-display text-xl">
          {detail.value.item.target_text}
        </p>
      </div>
    </main>
  );
}
