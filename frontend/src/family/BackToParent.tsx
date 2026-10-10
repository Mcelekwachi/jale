import { useEffect, useState } from "react";

import { Button } from "../components/Button";
import { useUiStrings } from "../i18n/useUiStrings";
import { apiFetch } from "../lib/api";
import { switchProfile } from "./switchProfile";

/** Leave child mode. Asks for the parent PIN when one is set. */
export function BackToParent({ label }: { label?: string }) {
  const strings = useUiStrings().family;
  const [hasPin, setHasPin] = useState<boolean | null>(null);
  const [asking, setAsking] = useState(false);
  const [pin, setPin] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void apiFetch<{ has_pin: boolean }>("/v1/me/pin", { authenticated: true })
      .then((result) => active && setHasPin(result.has_pin))
      .catch(() => active && setHasPin(true)); // when unsure, keep the lock on
    return () => {
      active = false;
    };
  }, []);

  async function leave() {
    setBusy(true);
    setMessage(null);
    try {
      await switchProfile(null);
    } catch {
      setMessage(strings.switchOffline);
      setBusy(false);
    }
  }

  async function unlock() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await apiFetch<{ valid: boolean }>("/v1/me/pin/verify", {
        method: "POST",
        authenticated: true,
        body: JSON.stringify({ pin }),
      });
      if (!result.valid) {
        setMessage(strings.pinWrong);
        setBusy(false);
        return;
      }
    } catch {
      setMessage(strings.saveError);
      setBusy(false);
      return;
    }
    await leave();
  }

  if (!asking)
    return (
      <div className="space-y-2">
        <Button
          variant="secondary"
          disabled={hasPin === null}
          busy={busy}
          onClick={() => (hasPin ? setAsking(true) : void leave())}
        >
          {label ?? strings.backToParent}
        </Button>
        {message && <p role="alert">{message}</p>}
      </div>
    );
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        void unlock();
      }}
    >
      <label className="grid gap-2 font-semibold text-indigo-deep">
        {strings.enterPin}
        <input
          type="password"
          inputMode="numeric"
          autoComplete="off"
          value={pin}
          onChange={(event) => setPin(event.target.value)}
          className="min-h-11 rounded-xl border border-sand bg-white px-3"
        />
      </label>
      {message && <p role="alert">{message}</p>}
      <Button type="submit" busy={busy}>
        {strings.unlock}
      </Button>
    </form>
  );
}
