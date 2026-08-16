import { useRef, useState } from "react";

export function AudioButton({
  url,
  state,
}: {
  url?: string | null;
  state: string;
}) {
  const audio = useRef<{ url: string; element: HTMLAudioElement } | null>(null);
  const [error, setError] = useState(false);
  if (state === "missing" || !url)
    return (
      <button
        type="button"
        disabled
        className="min-h-11 rounded-xl border border-sand px-4 text-sm text-muted"
      >
        🔊 Audio coming soon
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
        🔊 Play audio{state === "placeholder" ? " · sample" : ""}
      </button>
      {error && (
        <p role="status" className="text-sm text-terracotta-dark">
          Audio could not play.
        </p>
      )}
    </div>
  );
}
