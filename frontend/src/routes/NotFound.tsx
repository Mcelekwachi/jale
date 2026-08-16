import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <main className="grid min-h-dvh place-content-center bg-warm p-5">
      <section className="max-w-lg rounded-3xl bg-cream p-8 text-center shadow-card">
        <h1 className="font-display text-3xl text-indigo-deep">
          Page not found
        </h1>
        <p className="mt-3 text-muted">
          That page does not exist or may have moved.
        </p>
        <Link
          className="mt-6 inline-block rounded-xl bg-indigo-deep px-5 py-3 font-semibold text-white"
          to="/"
        >
          Home
        </Link>
      </section>
    </main>
  );
}
