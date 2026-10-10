import { useEffect, useState } from "react";

import { Button } from "../components/Button";
import { ErrorMessage } from "../components/ErrorMessage";
import { useUiStrings } from "../i18n/useUiStrings";
import { ApiError, apiFetch } from "../lib/api";
import type { ChildProfile } from "../lib/types";
import { switchProfile } from "./switchProfile";

function download(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Parent area: child profiles, consent, data export and deletion, PIN. */
export function FamilySection({
  onAccountDeleted,
}: {
  onAccountDeleted: () => void;
}) {
  const strings = useUiStrings().family;
  const thisYear = new Date().getFullYear();
  const [children, setChildren] = useState<ChildProfile[]>([]);
  const [hasPin, setHasPin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [nickname, setNickname] = useState("");
  const [birthYear, setBirthYear] = useState(thisYear - 8);
  const [consent, setConsent] = useState(false);
  const [pin, setPin] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (caught) {
      setError(
        caught instanceof ApiError || caught instanceof Error
          ? caught.message
          : strings.saveError,
      );
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let active = true;
    void Promise.all([
      apiFetch<ChildProfile[]>("/v1/me/children", { authenticated: true }),
      apiFetch<{ has_pin: boolean }>("/v1/me/pin", { authenticated: true }),
    ])
      .then(([list, pinStatus]) => {
        if (!active) return;
        setChildren(list);
        setHasPin(pinStatus.has_pin);
      })
      .catch(() => active && setError(strings.loadError));
    return () => {
      active = false;
    };
  }, [strings.loadError]);

  const addChild = () =>
    run(async () => {
      const child = await apiFetch<ChildProfile>("/v1/me/children", {
        method: "POST",
        authenticated: true,
        body: JSON.stringify({
          nickname,
          birth_year: birthYear,
          consent,
        }),
      });
      setChildren((current) => [...current, child]);
      setNickname("");
      setConsent(false);
    });

  const removeChild = (id: string) =>
    run(async () => {
      await apiFetch(`/v1/me/children/${id}`, {
        method: "DELETE",
        authenticated: true,
      });
      setChildren((current) => current.filter((child) => child.id !== id));
      setConfirming(null);
    });

  const exportData = (path: string, filename: string) =>
    run(async () => {
      download(
        filename,
        await apiFetch<unknown>(path, { authenticated: true }),
      );
    });

  const savePin = () =>
    run(async () => {
      await apiFetch("/v1/me/pin", {
        method: "PUT",
        authenticated: true,
        body: JSON.stringify({ pin }),
      });
      setHasPin(true);
      setPin("");
      setNotice(strings.pinSaved);
    });

  const deleteAccount = () =>
    run(async () => {
      await apiFetch("/v1/me?confirm=true", {
        method: "DELETE",
        authenticated: true,
      });
      onAccountDeleted();
    });

  const years = Array.from({ length: 18 }, (_, index) => thisYear - index);
  return (
    <section
      id="family"
      className="space-y-5 rounded-[2rem] bg-cream p-6 shadow-card"
    >
      <h2 className="font-display text-2xl font-semibold text-indigo-deep">
        {strings.title}
      </h2>
      <p>{strings.intro}</p>
      {error && <ErrorMessage message={error} />}
      {notice && <p role="status">{notice}</p>}

      {children.length === 0 ? (
        <p>{strings.none}</p>
      ) : (
        <ul className="space-y-3">
          {children.map((child) => (
            <li key={child.id} className="space-y-2 rounded-2xl bg-white p-4">
              <p className="font-semibold text-indigo-deep">
                {child.nickname} · {child.birth_year}
              </p>
              <Button
                disabled={busy}
                onClick={() =>
                  void switchProfile(child.id).catch(() =>
                    setError(strings.switchOffline),
                  )
                }
              >
                {strings.switchTo}
              </Button>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() =>
                  void exportData(
                    `/v1/me/children/${child.id}/export`,
                    `jale-${child.nickname}.json`,
                  )
                }
              >
                {strings.download}
              </Button>
              {confirming === child.id ? (
                <div className="space-y-2">
                  <p>{strings.removeConfirm}</p>
                  <Button
                    disabled={busy}
                    onClick={() => void removeChild(child.id)}
                  >
                    {strings.confirmYes}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setConfirming(null)}
                  >
                    {strings.cancel}
                  </Button>
                </div>
              ) : (
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => setConfirming(child.id)}
                >
                  {strings.remove}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          void addChild();
        }}
      >
        <label className="grid gap-2 font-semibold text-indigo-deep">
          {strings.nickname}
          <input
            value={nickname}
            maxLength={30}
            onChange={(event) => setNickname(event.target.value)}
            className="min-h-11 rounded-xl border border-sand bg-white px-3"
          />
          <span className="text-sm font-normal text-muted">
            {strings.nicknameHint}
          </span>
        </label>
        <label className="grid gap-2 font-semibold text-indigo-deep">
          {strings.birthYear}
          <select
            value={birthYear}
            onChange={(event) => setBirthYear(Number(event.target.value))}
            className="min-h-11 rounded-xl border border-sand bg-white px-3"
          >
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
        <label className="flex gap-3">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            className="mt-1 size-5"
          />
          <span>{strings.consent}</span>
        </label>
        <Button
          type="submit"
          busy={busy}
          disabled={!consent || !nickname.trim()}
        >
          {strings.addChild}
        </Button>
      </form>

      <div className="space-y-3">
        <h3 className="font-display text-xl font-semibold text-indigo-deep">
          {strings.pinTitle}
        </h3>
        <p>{strings.pinIntro}</p>
        {hasPin && <p>{strings.pinIsSet}</p>}
        <label className="grid gap-2 font-semibold text-indigo-deep">
          {strings.pinLabel}
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            className="min-h-11 rounded-xl border border-sand bg-white px-3"
          />
        </label>
        <Button
          variant="secondary"
          busy={busy}
          disabled={!/^\d{4,8}$/.test(pin)}
          onClick={() => void savePin()}
        >
          {strings.pinSave}
        </Button>
      </div>

      <div className="space-y-3">
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => void exportData("/v1/me/export", "jale-my-data.json")}
        >
          {strings.exportAll}
        </Button>
        {confirming === "account" ? (
          <div className="space-y-2">
            <p>{strings.deleteAccountConfirm}</p>
            <Button disabled={busy} onClick={() => void deleteAccount()}>
              {strings.confirmYes}
            </Button>
            <Button variant="secondary" onClick={() => setConfirming(null)}>
              {strings.cancel}
            </Button>
          </div>
        ) : (
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => setConfirming("account")}
          >
            {strings.deleteAccount}
          </Button>
        )}
      </div>
    </section>
  );
}
