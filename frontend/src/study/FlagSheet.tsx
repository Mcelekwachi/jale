import { useState } from "react";
import { apiFetch } from "../lib/api";

const reasons = {
  bad_audio: "The audio is wrong or unclear",
  wrong_translation: "The translation is wrong",
  cultural_inaccuracy: "The cultural note is inaccurate",
  spelling_or_tone: "The spelling or tone marks are wrong",
  offensive: "This is offensive",
  other: "Something else",
} as const;
type Reason = keyof typeof reasons;
export function FlagSheet({
  contentId,
  metaLanguage,
}: {
  contentId: number;
  metaLanguage: string;
}) {
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
      setMessage(
        reported ? "Thanks, already reported" : "Thanks for helping us improve",
      );
      setReported(true);
      setOpen(false);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not send report");
    }
  };
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="min-h-11 rounded-xl border border-sand px-4 font-semibold"
      >
        ⚑ Flag
      </button>
      {message && (
        <p role="status" className="mt-2 text-sm">
          {message}
        </p>
      )}
      {open && (
        <div
          role="dialog"
          aria-label="Report this item"
          className="fixed inset-x-0 bottom-0 z-10 mx-auto max-w-lg rounded-t-[2rem] bg-cream p-6 shadow-card"
        >
          <h2 className="font-display text-2xl text-indigo-deep">
            What needs attention?
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
            Optional note
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
              Send report
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="min-h-11 px-4"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
