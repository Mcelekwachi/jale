import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { Spinner } from "../components/Spinner";
import { apiFetch } from "../lib/api";
import type {
  AdminContentDetail,
  AdminContentPage,
  AdminContentState,
  AdminTranslationSlot,
  AdminTranslationState,
  AdminVerificationResult,
  AudioState,
  ContentStatus,
  Difficulty,
} from "../lib/types";

type LoadState<T> =
  | { status: "loading" }
  | { status: "loaded"; value: T }
  | { status: "error"; message: string };

type Filters = {
  q: string;
  content_type: string;
  difficulty: string;
  category: string;
  status: string;
  verified: string;
  audio_state: string;
  has_flags: string;
  missing_translation: string;
  offset: number;
};

const emptyFilters: Filters = {
  q: "",
  content_type: "",
  difficulty: "",
  category: "",
  status: "",
  verified: "",
  audio_state: "",
  has_flags: "",
  missing_translation: "",
  offset: 0,
};

const fieldClass =
  "min-h-11 w-full rounded-xl border border-sand bg-white px-3 py-2 text-ink focus:border-ochre focus:outline-none";
const actionClass =
  "rounded-xl bg-indigo-deep px-4 py-2.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60";
const secondaryClass =
  "rounded-xl border border-ochre px-4 py-2.5 font-semibold text-indigo-deep hover:bg-ochre-soft";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function queryFor(filters: Filters): string {
  const query = new URLSearchParams({ limit: "50", offset: String(filters.offset) });
  for (const [key, value] of Object.entries(filters)) {
    if (key !== "offset" && value !== "") query.set(key, String(value));
  }
  return query.toString();
}

function title(value: string) {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function languageName(code: string) {
  return ({ eng: "English", nld: "Dutch" } as Record<string, string>)[code] ?? code;
}

export function AdminContentList() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState<LoadState<AdminContentPage>>({ status: "loading" });
  const query = useMemo(() => queryFor(filters), [filters]);

  useEffect(() => {
    let active = true;
    setPage({ status: "loading" });
    void apiFetch<AdminContentPage>(`/v1/admin/content?${query}`, {
      authenticated: true,
    })
      .then((value) => active && setPage({ status: "loaded", value }))
      .catch(
        (error: unknown) =>
          active &&
          setPage({ status: "error", message: errorMessage(error, "Unable to load content") }),
      );
    return () => {
      active = false;
    };
  }, [query]);

  const update = (values: Partial<Filters>) =>
    setFilters((current) => ({ ...current, ...values, offset: values.offset ?? 0 }));

  return (
    <main className="min-h-dvh bg-warm p-5 sm:p-8">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link className="text-sm font-semibold text-indigo-rich underline" to="/admin">
              Flag queue
            </Link>
            <h1 className="mt-2 font-display text-3xl text-indigo-deep">
              Content management
            </h1>
          </div>
          <div className="flex flex-wrap gap-2" aria-label="Daily queues">
            <button className={secondaryClass} type="button" onClick={() => update({ verified: "false", has_flags: "", missing_translation: "" })}>
              Unverified
            </button>
            <button className={secondaryClass} type="button" onClick={() => update({ has_flags: "true", verified: "", missing_translation: "" })}>
              Flagged
            </button>
            <button className={secondaryClass} type="button" onClick={() => update({ missing_translation: "nld", verified: "", has_flags: "" })}>
              Missing Dutch translation
            </button>
          </div>
        </div>

        <section className="mt-6 rounded-2xl bg-cream p-4 shadow-card" aria-label="Content filters">
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
            <label className="text-sm font-semibold text-indigo-deep">
              Search
              <input className={`${fieldClass} mt-1`} value={filters.q} onChange={(event) => update({ q: event.target.value })} />
            </label>
            <FilterSelect label="Content type" value={filters.content_type} options={["word", "phrase", "proverb", "story"]} onChange={(content_type) => update({ content_type })} />
            <FilterSelect label="Difficulty" value={filters.difficulty} options={["beginner", "intermediate", "advanced", "native"]} onChange={(difficulty) => update({ difficulty })} />
            <label className="text-sm font-semibold text-indigo-deep">
              Category slug
              <input className={`${fieldClass} mt-1`} value={filters.category} onChange={(event) => update({ category: event.target.value })} />
            </label>
            <FilterSelect label="Status" value={filters.status} options={["draft", "published", "hidden"]} onChange={(status) => update({ status })} />
            <FilterSelect label="Verified" value={filters.verified} options={["true", "false"]} onChange={(verified) => update({ verified })} />
            <FilterSelect label="Audio state" value={filters.audio_state} options={["missing", "placeholder", "verified"]} onChange={(audio_state) => update({ audio_state })} />
            <FilterSelect label="Has flags" value={filters.has_flags} options={["true", "false"]} onChange={(has_flags) => update({ has_flags })} />
            <label className="flex items-end">
              <button className={`${secondaryClass} w-full`} type="button" onClick={() => setFilters(emptyFilters)}>
                Clear filters
              </button>
            </label>
          </div>
        </section>

        {page.status === "loading" && <Spinner label="Loading admin content" />}
        {page.status === "error" && <div className="mt-6"><ErrorMessage message={page.message} /></div>}
        {page.status === "loaded" && (
          <>
            <p className="mt-5 text-sm text-muted">{page.value.total} items</p>
            {page.value.items.length === 0 ? (
              <p className="mt-3 rounded-2xl bg-cream p-6 text-muted shadow-card">No content matches these filters.</p>
            ) : (
              <div className="mt-3 overflow-x-auto rounded-2xl bg-cream shadow-card">
                <table className="w-full border-collapse text-left text-sm">
                  <thead className="bg-indigo-deep text-cream">
                    <tr>{["Igbo", "Type", "Translation", "Status", "Verified", "Audio", "Flags"].map((heading) => <th className="px-4 py-3" key={heading}>{heading}</th>)}</tr>
                  </thead>
                  <tbody>
                    {page.value.items.map((item) => (
                      <tr
                        key={item.id}
                        tabIndex={0}
                        aria-label={`Edit ${item.target_text}`}
                        className={`cursor-pointer border-t border-sand hover:bg-ochre-soft ${item.status === "published" ? "" : "bg-terracotta-soft/40 opacity-80"}`}
                        onClick={() => navigate(`/admin/content/${item.id}`)}
                        onKeyDown={(event) => event.key === "Enter" && navigate(`/admin/content/${item.id}`)}
                      >
                        <td className="px-4 py-3 font-display text-base font-semibold text-indigo-deep">{item.target_text}</td>
                        <td className="px-4 py-3">{item.content_type}</td>
                        <td className="max-w-xs px-4 py-3 text-muted">{item.translation || "—"}</td>
                        <td className="px-4 py-3">{item.status}</td>
                        <td className="px-4 py-3">{item.verified ? "Yes" : "No"}</td>
                        <td className="px-4 py-3">{item.audio_state}</td>
                        <td className="px-4 py-3">{item.flag_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-5 flex items-center justify-end gap-3">
              <button className={secondaryClass} type="button" disabled={page.value.offset === 0} onClick={() => update({ offset: Math.max(0, page.value.offset - page.value.limit) })}>Previous</button>
              <button className={secondaryClass} type="button" disabled={page.value.offset + page.value.limit >= page.value.total} onClick={() => update({ offset: page.value.offset + page.value.limit })}>Next</button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="text-sm font-semibold text-indigo-deep">
      {label}
      <select className={`${fieldClass} mt-1`} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {options.map((option) => <option key={option} value={option}>{title(option)}</option>)}
      </select>
    </label>
  );
}

function verificationText(verified: boolean, name: string | null, at: string | null) {
  if (!verified) return "Not verified";
  const who = name || "an administrator";
  return `Verified by ${who}${at ? ` on ${new Date(at).toLocaleString()}` : ""}`;
}

function ItemEditor({ item, onUpdated, onVerify }: { item: AdminContentState; onUpdated: (item: AdminContentState) => void; onVerify: (verified: boolean, note: string) => Promise<void> }) {
  const [form, setForm] = useState({
    target_text: item.target_text ?? "",
    target_text_toned: item.target_text_toned ?? "",
    category: item.category ?? "",
    difficulty_level: item.difficulty_level ?? "beginner",
    audio_url: item.audio_url ?? "",
    audio_state: item.audio_state ?? "missing",
    status: item.status ?? "draft",
    sort_order: String(item.sort_order ?? 0),
    change_note: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.change_note.trim()) { setError("A change note is required before saving."); return; }
    setBusy(true); setError("");
    try {
      const updated = await apiFetch<AdminContentState>(`/v1/admin/content/${item.id}`, {
        authenticated: true,
        method: "PATCH",
        body: JSON.stringify({
          target_text: form.target_text,
          target_text_toned: form.target_text_toned || null,
          category: form.category || null,
          difficulty_level: form.difficulty_level as Difficulty,
          audio_url: form.audio_url || null,
          audio_state: form.audio_state as AudioState,
          status: form.status as ContentStatus,
          sort_order: Number(form.sort_order),
          change_note: form.change_note,
        }),
      });
      onUpdated(updated); setForm((current) => ({ ...current, change_note: "" }));
    } catch (caught) { setError(errorMessage(caught, "Unable to save item")); } finally { setBusy(false); }
  };

  return (
    <section className="rounded-2xl bg-cream p-5 shadow-card">
      <h2 className="font-display text-2xl text-indigo-deep">The item</h2>
      <dl className="mt-4 grid gap-3 rounded-xl bg-warm p-4 text-sm sm:grid-cols-3">
        <div><dt className="font-semibold">Source key</dt><dd>{item.source_key}</dd></div>
        <div><dt className="font-semibold">Language</dt><dd>{item.language}</dd></div>
        <div><dt className="font-semibold">Content type</dt><dd>{item.content_type}</dd></div>
      </dl>
      <p className="mt-2 text-sm text-muted">These fields define the item’s identity and cannot be edited.</p>
      <form className="mt-5 grid gap-4 sm:grid-cols-2" onSubmit={submit} noValidate>
        <TextField label="Target text" value={form.target_text} onChange={(value) => set("target_text", value)} display />
        <TextField label="Toned target text" value={form.target_text_toned} onChange={(value) => set("target_text_toned", value)} display />
        <TextField label="Category slug" value={form.category} onChange={(value) => set("category", value)} />
        <SelectField label="Difficulty" value={form.difficulty_level} options={["beginner", "intermediate", "advanced", "native"]} onChange={(value) => set("difficulty_level", value)} />
        <div>
          <TextField label="Audio URL" value={form.audio_url} onChange={(value) => set("audio_url", value)} />
          {form.audio_url && <a className="mt-2 inline-block text-sm text-indigo-rich underline" href={form.audio_url} target="_blank" rel="noreferrer">Open current audio</a>}
        </div>
        <SelectField label="Audio state" value={form.audio_state} options={["missing", "placeholder", "verified"]} onChange={(value) => set("audio_state", value)} />
        {form.audio_url && <audio className="w-full sm:col-span-2" controls src={form.audio_url}>Your browser cannot play this audio.</audio>}
        <SelectField label="Status" value={form.status} options={["draft", "published", "hidden"]} onChange={(value) => set("status", value)} />
        <TextField label="Sort order" type="number" value={form.sort_order} onChange={(value) => set("sort_order", value)} />
        <div className="sm:col-span-2"><TextField label="Item change note" value={form.change_note} onChange={(value) => set("change_note", value)} /><p className="mt-1 text-xs text-muted">Required so the audit trail explains why this change was made.</p></div>
        {error && <div className="sm:col-span-2"><ErrorMessage message={error} /></div>}
        <div className="flex flex-wrap items-center justify-between gap-3 sm:col-span-2">
          <p className="text-sm text-muted">{verificationText(item.verified, item.verified_by_name, item.verified_at)}</p>
          <div className="flex gap-2">
            <button className={secondaryClass} type="button" disabled={busy} onClick={() => form.change_note.trim() ? void onVerify(!item.verified, form.change_note) : setError("A change note is required before verification.")}>{item.verified ? "Unverify item" : "Verify item"}</button>
            <button className={actionClass} type="submit" disabled={busy}>{busy ? "Saving…" : "Save item"}</button>
          </div>
        </div>
      </form>
    </section>
  );
}

function TextField({ label, value, onChange, type = "text", display = false }: { label: string; value: string; onChange: (value: string) => void; type?: string; display?: boolean }) {
  return <label className="text-sm font-semibold text-indigo-deep">{label}<input aria-label={label} className={`${fieldClass} mt-1 ${display ? "font-display" : ""}`} type={type} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return <label className="text-sm font-semibold text-indigo-deep">{label}<select aria-label={label} className={`${fieldClass} mt-1`} value={value} onChange={(event) => onChange(event.target.value)}>{options.map((option) => <option key={option} value={option}>{title(option)}</option>)}</select></label>;
}

function TranslationEditor({ contentId, slot, contentType, onUpdated, onVerify }: { contentId: number; slot: AdminTranslationSlot; contentType: string; onUpdated: (state: AdminTranslationState) => void; onVerify: (verified: boolean, note: string) => Promise<void> }) {
  const name = languageName(slot.meta_language);
  const [editing, setEditing] = useState(slot.state !== null);
  const [form, setForm] = useState({ translation: slot.state?.translation ?? "", literal_translation: slot.state?.literal_translation ?? "", cultural_note: slot.state?.cultural_note ?? "", change_note: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (field: keyof typeof form, value: string) => setForm((current) => ({ ...current, [field]: value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.change_note.trim()) { setError("A change note is required before saving."); return; }
    setBusy(true); setError("");
    try {
      const updated = await apiFetch<AdminTranslationState>(`/v1/admin/content/${contentId}/translations/${slot.meta_language}`, {
        authenticated: true,
        method: "PATCH",
        body: JSON.stringify({ translation: form.translation, literal_translation: form.literal_translation || null, cultural_note: form.cultural_note || null, change_note: form.change_note }),
      });
      onUpdated(updated); setEditing(true); setForm((current) => ({ ...current, change_note: "" }));
    } catch (caught) { setError(errorMessage(caught, "Unable to save translation")); } finally { setBusy(false); }
  };

  if (!editing) {
    return <section className="rounded-2xl border-2 border-dashed border-ochre bg-cream p-5"><h3 className="font-display text-xl text-indigo-deep">{name}</h3><p className="mt-2 font-semibold text-terracotta-dark">No {name} translation yet</p><button className={`${actionClass} mt-4`} type="button" onClick={() => setEditing(true)}>Create {name} translation</button></section>;
  }

  return (
    <section className="rounded-2xl bg-cream p-5 shadow-card">
      <h3 className="font-display text-xl text-indigo-deep">{name}</h3>
      {slot.state?.translation === "" && <p className="mt-2 font-semibold text-ochre">{name} translation exists but is blank</p>}
      <form className="mt-4 grid gap-4" onSubmit={submit} noValidate>
        <label className="text-sm font-semibold text-indigo-deep">{name} translation<textarea aria-label={`${name} translation`} className={`${fieldClass} mt-1 min-h-24`} value={form.translation} onChange={(event) => set("translation", event.target.value)} /></label>
        <label className="text-sm font-semibold text-indigo-deep">Literal translation<textarea aria-label={`${name} literal translation`} className={`${fieldClass} mt-1 min-h-20`} value={form.literal_translation} onChange={(event) => set("literal_translation", event.target.value)} /></label>
        <label className="text-sm font-semibold text-indigo-deep">Cultural note {contentType === "proverb" && <span className="text-terracotta-dark">(required for proverbs)</span>}<textarea aria-label={`${name} cultural note`} aria-required={contentType === "proverb"} className={`${fieldClass} mt-1 min-h-24`} value={form.cultural_note} onChange={(event) => set("cultural_note", event.target.value)} /></label>
        <div><TextField label={`${name} change note`} value={form.change_note} onChange={(value) => set("change_note", value)} /><p className="mt-1 text-xs text-muted">Required so the audit trail explains why this change was made.</p></div>
        {error && <ErrorMessage message={error} />}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted">{verificationText(slot.state?.verified ?? false, slot.state?.verified_by_name ?? null, slot.state?.verified_at ?? null)}</p>
          <div className="flex gap-2">
            {slot.state && <button className={secondaryClass} type="button" disabled={busy} onClick={() => form.change_note.trim() ? void onVerify(!slot.state!.verified, form.change_note) : setError("A change note is required before verification.")}>{slot.state.verified ? `Unverify ${name}` : `Verify ${name}`}</button>}
            <button className={actionClass} type="submit" disabled={busy}>{busy ? "Saving…" : `Save ${name} translation`}</button>
          </div>
        </div>
      </form>
    </section>
  );
}

export function AdminContentDetailRoute() {
  const { contentId } = useParams();
  const [detail, setDetail] = useState<LoadState<AdminContentDetail>>({ status: "loading" });

  useEffect(() => {
    let active = true;
    void apiFetch<AdminContentDetail>(`/v1/admin/content/${contentId}`, { authenticated: true })
      .then((value) => active && setDetail({ status: "loaded", value }))
      .catch((error: unknown) => active && setDetail({ status: "error", message: errorMessage(error, "Unable to load content detail") }));
    return () => { active = false; };
  }, [contentId]);

  if (detail.status === "loading") return <Spinner label="Loading content detail" fullScreen />;
  if (detail.status === "error") return <ErrorMessage message={detail.message} />;

  const updateItem = (item: AdminContentState) => setDetail((current) => current.status === "loaded" ? { status: "loaded", value: { ...current.value, item } } : current);
  const updateTranslation = (translation: AdminTranslationState) => setDetail((current) => current.status === "loaded" ? { status: "loaded", value: { ...current.value, translations: current.value.translations.map((slot) => slot.meta_language === translation.meta_language ? { ...slot, state: translation } : slot) } } : current);
  const verify = async (verified: boolean, metaLanguage: string | null, note: string) => {
    const result = await apiFetch<AdminVerificationResult>(`/v1/admin/content/${contentId}/${verified ? "verify" : "unverify"}`, { authenticated: true, method: "POST", body: JSON.stringify({ meta_language: metaLanguage, change_note: note }) });
    if (result.target === "content" && result.content) updateItem(result.content);
    if (result.target === "translation" && result.translation) updateTranslation(result.translation);
  };

  return (
    <main className="min-h-dvh bg-warm p-5 sm:p-8">
      <div className="mx-auto max-w-6xl">
        <Link className="text-indigo-rich underline" to="/admin/content">Back to content</Link>
        <h1 className="mt-4 font-display text-3xl text-indigo-deep">Edit content</h1>
        <p className="mt-2 font-display text-xl">{detail.value.item.target_text}</p>
        <div className="mt-6"><ItemEditor item={detail.value.item} onUpdated={updateItem} onVerify={(verified, note) => verify(verified, null, note)} /></div>
        <section className="mt-8">
          <h2 className="font-display text-2xl text-indigo-deep">Translations</h2>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            {detail.value.translations.map((slot) => <TranslationEditor key={slot.meta_language} contentId={detail.value.item.id} slot={slot} contentType={detail.value.item.content_type} onUpdated={updateTranslation} onVerify={(verified, note) => verify(verified, slot.meta_language, note)} />)}
          </div>
        </section>
      </div>
    </main>
  );
}
