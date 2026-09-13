import { useState } from "react";
import { apiFetch } from "../lib/api";
import { useUiStrings } from "../i18n/useUiStrings";

type Reason =
  | "bad_audio"
  | "wrong_translation"
  | "cultural_inaccuracy"
  | "spelling_or_tone"
  | "offensive"
  | "other";
export function FlagSheet({
  contentId,
  metaLanguage,
}: {
  contentId: number;
  metaLanguage: string;
}) {
  const strings = useUiStrings().study;
  const reasons: Record<Reason, string> = {
    bad_audio: strings.badAudio,
    wrong_translation: strings.wrongTranslation,
    cultural_inaccuracy: strings.culturalInaccuracy,
    spelling_or_tone: strings.spellingOrTone,
    offensive: strings.offensive,
    other: strings.other,
  };
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<Reason | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [reported, setReported] = useState(false);
  const submit = async () => {
    if (!reason) return;
    try {
      await apiFetch(`/v1/content/${contentId}/flag`, {
        method: "POST",
        authenticated: true,
        body: JSON.stringify({
          reason,
          note: note || null,
          ...(["wrong_translation", "cultural_inaccuracy"].includes(reason)
            ? { meta_language: metaLanguage }
            : {}),
        }),
      });
      setMessage(reported ? strings.alreadyReported : strings.reportThanks);
      setReported(true);
      setOpen(false);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : strings.reportError);
    }
  };
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="min-h-11 rounded-xl border border-sand px-4 font-semibold"
      >
        {strings.flag}
      </button>
      {message && (
        <p role="status" className="mt-2 text-sm">
          {message}
        </p>
      )}
      {open && (
        <div
          role="dialog"
          aria-label={strings.reportItem}
          className="fixed inset-x-0 bottom-0 z-10 mx-auto max-w-lg rounded-t-[2rem] bg-cream p-6 shadow-card"
        >
          <h2 className="font-display text-2xl text-indigo-deep">
            {strings.attention}
          </h2>
          <fieldset className="mt-4 space-y-2">
            {Object.entries(reasons).map(([value, label]) => (
              <label key={value} className="flex min-h-11 items-center gap-3">
                <input
                  type="radio"
                  name="reason"
                  checked={reason === value}
                  onChange={() => setReason(value as Reason)}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <label className="mt-3 grid gap-2">
            {strings.optionalNote}
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="min-h-20 rounded-xl border border-sand p-3"
            />
          </label>
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!reason}
              className="min-h-11 flex-1 rounded-xl bg-indigo-deep px-4 font-bold text-cream"
            >
              {strings.sendReport}
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="min-h-11 px-4"
            >
              {strings.cancel}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
