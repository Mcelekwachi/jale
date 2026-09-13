import { Link } from "react-router-dom";
import { useUiStrings } from "../i18n/useUiStrings";

export function NotFound() {
  const strings = useUiStrings().shared;
  return (
    <main className="grid min-h-dvh place-content-center bg-warm p-5">
      <section className="max-w-lg rounded-3xl bg-cream p-8 text-center shadow-card">
        <h1 className="font-display text-3xl text-indigo-deep">
          {strings.pageNotFound}
        </h1>
        <p className="mt-3 text-muted">{strings.pageMissing}</p>
        <Link
          className="mt-6 inline-block rounded-xl bg-indigo-deep px-5 py-3 font-semibold text-white"
          to="/"
        >
          {strings.home}
        </Link>
      </section>
    </main>
  );
}
