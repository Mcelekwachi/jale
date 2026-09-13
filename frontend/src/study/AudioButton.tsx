import { useRef, useState } from "react";

export function AudioButton({
  url,
  state,
  labels,
}: {
  url?: string | null;
  state: string;
  labels?: {
    comingSoon: string;
    play: string;
    sample: string;
    error: string;
  };
}) {
  const copy = labels ?? {
    comingSoon: "🔊 Audio coming soon",
    play: "🔊 Play audio",
    sample: "sample",
    error: "Audio could not play.",
  };
  const audio = useRef<{ url: string; element: HTMLAudioElement } | null>(null);
  const [error, setError] = useState(false);
  if (state === "missing" || !url)
    return (
      <button
        type="button"
        disabled
        className="min-h-11 rounded-xl border border-sand px-4 text-sm text-muted"
      >
        {copy.comingSoon}
      </button>
    );
  const play = async () => {
    try {
      if (audio.current?.url !== url) {
        audio.current = { url, element: new Audio(url) };
      }
      await audio.current.element.play();
      setError(false);
    } catch {
      setError(true);
    }
  };
  return (
    <div>
      <button
        type="button"
        onClick={() => void play()}
        className="min-h-11 rounded-xl border border-ochre px-4 font-semibold"
      >
        {copy.play}
        {state === "placeholder" ? ` · ${copy.sample}` : ""}
      </button>
      {error && (
        <p role="status" className="text-sm text-terracotta-dark">
          {copy.error}
        </p>
      )}
    </div>
  );
}
