import { useEffect, useState } from "react";
import { useUiStrings } from "../i18n/useUiStrings";

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

const COMPLETED_KEY = "jale:completed-study-session";
const DISMISSED_KEY = "jale:install-prompt-dismissed";

function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches === true ||
    Boolean((navigator as Navigator & { standalone?: boolean }).standalone)
  );
}

function isIosSafari(): boolean {
  const agent = navigator.userAgent;
  return (
    /iPad|iPhone|iPod/.test(agent) &&
    /Safari/.test(agent) &&
    !/CriOS|FxiOS|EdgiOS/.test(agent)
  );
}

export function PwaPrompts() {
  const strings = useUiStrings().shared;
  const [completed, setCompleted] = useState(
    () => localStorage.getItem(COMPLETED_KEY) === "true",
  );
  const [installEvent, setInstallEvent] = useState<InstallPromptEvent | null>(
    null,
  );
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISSED_KEY) === "true",
  );

  useEffect(() => {
    const capture = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as InstallPromptEvent);
    };
    const markCompleted = () => setCompleted(true);
    window.addEventListener("beforeinstallprompt", capture);
    window.addEventListener("jale:study-session-completed", markCompleted);
    return () => {
      window.removeEventListener("beforeinstallprompt", capture);
      window.removeEventListener("jale:study-session-completed", markCompleted);
    };
  }, []);

  if (!completed || dismissed || isStandalone()) return null;
  const dismiss = () => {
    localStorage.setItem(DISMISSED_KEY, "true");
    setDismissed(true);
  };
  const ios = isIosSafari();
  if (!ios && !installEvent) return null;

  return (
    <aside
      className="fixed inset-x-4 bottom-4 z-40 mx-auto max-w-md rounded-2xl bg-cream p-5 shadow-card"
      aria-label={strings.installLabel}
    >
      <button
        type="button"
        onClick={dismiss}
        aria-label={strings.dismissInstall}
        className="float-right min-h-11 px-3"
      >
        ×
      </button>
      <h2 className="font-display text-xl text-indigo-deep">
        {strings.addToHome}
      </h2>
      {ios ? (
        <p className="mt-2 text-sm">{strings.iosInstall}</p>
      ) : (
        <button
          type="button"
          className="mt-4 min-h-11 rounded-xl bg-indigo-deep px-5 font-bold text-cream"
          onClick={() => {
            void installEvent?.prompt();
            setInstallEvent(null);
          }}
        >
          {strings.add}
        </button>
      )}
    </aside>
  );
}
